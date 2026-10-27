"""Revision/scope/scenario-bound analysis without shared mutable model globals."""
import copy
from functools import lru_cache
from pathlib import Path
from .storage import digest, read, revision
from .project import snapshot
from decision_analysis.partial_candidates import VERSION as CANDIDATE_VERSION, generate
from decision_analysis.visibility_scenarios import VERSION as SCENARIO_VERSION, SCENARIOS, state_for
from decision_analysis.partial_q2 import VERSION as PARTIAL_VERSION, evaluate
from decision_analysis.tactical_rules import softmax
from decision_analysis.sensitivity import compare

MODEL = Path(__file__).resolve().parents[1] / 'data/decision-analysis/models/fold-0.json'


@lru_cache(maxsize=1)
def frozen_model():
    model=read(MODEL)
    if len(model['xt']) != 96:
        raise ValueError('Invalid frozen xT model')
    return model


def select(data,owner,root=None):
    required={'video_id','revision_id','frame_index','visibility_scope','selected_player_ids','assumption_set_id','include_shot'}
    if not isinstance(data,dict) or set(data)!=required or type(data['include_shot']) is not bool:
        raise ValueError('Expected complete versioned video selection')
    if data['assumption_set_id'] not in (*SCENARIOS,'observed_only','full'):
        raise ValueError('Unknown assumption set')
    record=revision(data['video_id'],data['revision_id'],owner,root)
    s=snapshot(record,data['frame_index'],data['visibility_scope'],data['selected_player_ids'])
    if data['assumption_set_id']=='full' and s['observation_mode']!='full_observation':
        raise ValueError('Full Q2 requires explicit complete coverage and both known keepers')
    if s['observation_mode']=='full_observation' and data['assumption_set_id']!='full':
        raise ValueError('Complete verified video should use full mode, not hypothetical extra defenders')
    return s


def full_rows(state,xt):
    """Call unchanged full Q2 only for a genuinely complete verified video frame."""
    from decision_analysis.q2 import evaluate as full_evaluate
    s=copy.deepcopy(state);mapping={};back={}
    for t,prefix in [('HOME','H'),('AWAY','A')]:
        group=sorted([p for p in s['players'] if p['team']==t],key=lambda p:p['position']!='GK')
        if len(group)!=11 or sum(p['position']=='GK' for p in group)!=1:
            raise ValueError('Incomplete full video state')
        for i,p in enumerate(group,1):mapping[p['id']]=prefix+str(i).zfill(2)
    back={v:k for k,v in mapping.items()}
    for p in s['players']:p.update(id=mapping[p['id']],team=0 if p['team']=='HOME' else 1)
    s.update(actor=mapping[s['actor']],team=0 if s['team']=='HOME' else 1,period=1,score=[0,0],ball=[*s['ball'],0.,0.,0.,0.],
        ratings=[dict(attack=1.,defense=1.,passing=1.,pressing=1.)]*2,
        attacking_direction={'HOME':'positive_x' if (state['direction']==1)==(state['team']=='HOME') else 'negative_x'})
    s['attacking_direction']['AWAY']='negative_x' if s['attacking_direction']['HOME']=='positive_x' else 'positive_x'
    s['t_ms']=0  # No fabricated match clock; neutral context explicitly recorded.
    result=full_evaluate(s,xt)
    for a in result:
        for key in ('recipient','defender'):a[key]=back.get(a.get(key),a.get(key))
        if a['kind']=='pass':a['key']='pass:'+a['recipient']
    return result


def compute(s,scenario,include_shot=False):
    model=frozen_model();mode=s['observation_mode'];ready=s['observation_quality']['ready']
    model_version='outcome-3.0' if mode=='full_observation' else PARTIAL_VERSION
    binding={k:s[k] for k in ('snapshot_id','video_id','revision_id','frame_index','visibility_scope_id','observation_mode')}
    binding.update(assumption_set_id=scenario,scenario_model_version=SCENARIO_VERSION,q2_model_version=model_version)
    key=digest([binding,include_shot,model['model_id'],CANDIDATE_VERSION])
    if not ready:
        return dict(**binding,status='needs_confirmation',level=1,candidate_set_id=None,analysis_id=key,candidate_actions=[],ranking=[],snapshot=s,observation_quality=s['observation_quality'],observed_counts=dict(attacking_players=sum(p['team_id']==s['possession_team'] for p in s['observed_players']),available_teammates=len(s['observed_teammates']),visible_defenders=len(s['observed_opponents'])),limitations=s['limitations'],missing_information=s['unknown_state'])
    state,assumptions=state_for(s,'observed_only' if scenario=='full' else scenario,include_shot)
    # Candidate identity depends on observed state and policy, not virtual opponents.
    visible_state,_=state_for(s,'observed_only',False)
    actions=generate(visible_state,False)
    if include_shot:
        shot=next(a for a in generate(state,True) if a['kind']=='shot');actions.append(shot)
    complete_rows=full_rows(state,model['xt']) if mode=='full_observation' else None
    if complete_rows is not None:actions=complete_rows
    cid='video-candidates-'+digest([s['snapshot_id'],CANDIDATE_VERSION,model['model_id'],model_version,include_shot,[a['key'] for a in actions]])
    base=dict(**binding,observation_quality=s['observation_quality'],candidate_set_id=cid,analysis_id=key,snapshot=s,assumptions=assumptions,missing_information=s['unknown_state'],
        observed_counts=dict(attacking_players=len(s['observed_teammates'])+1,available_teammates=len(s['observed_teammates']),visible_defenders=len(s['observed_opponents'])),
        candidate_actions=[dict(a,action_id=a['key'],action_type=a['kind']) for a in actions],limitations=s['limitations'],
        model=dict(tail_model_id=model['model_id'],temperature=model.get('temperature',.05),q2_model_version=model_version,scenario_model_version=SCENARIO_VERSION,
                   evaluation='Full Q2 unvalidated video transfer with neutral match/team context' if mode=='full_observation' else 'Conditional partial two-step Q2, not full-field optimality'),ranking=[])
    if scenario=='observed_only':
        base.update(status='candidate_discovery',level=1,diagnostic=dict(nearest_visible_defender='unknown' if not s['observed_opponents'] else 'see observed positions',ranking_available=False))
        return base
    rows=complete_rows if complete_rows is not None else evaluate(state,model['xt'],2,include_shot)
    ids={a['key'] for a in actions};rows=[r for r in rows if r['key'] in ids]
    weighted=softmax(rows,model.get('temperature',.05));rank=0
    for a in weighted:
        eligible=a.get('supported') and a.get('q') is not None
        if eligible:rank+=1
        row=dict(a,action_id=a['key'],action_type=a['kind'],rank=rank if eligible else None,
            source_type='model_derived_conditional' if mode=='partial_observation' else 'unvalidated_full_video_transfer',
            evidence_id='video-evidence:'+digest([key,a['key']]),opportunity=a.get('opportunity','Two-step model continuation; neutral team and match context.'),
            main_risk=a.get('main_risk','Geometric branch probabilities and video transfer are unvalidated assumptions.'))
        if eligible:base['ranking'].append(row)
    base.update(status=('conditional_ranking' if mode=='partial_observation' else 'full_q2') if base['ranking'] else 'candidate_discovery',level=(2 if mode=='partial_observation' else 3) if base['ranking'] else 1)
    return base


def analyze(data,owner,root=None):
    return compute(select(data,owner,root),data['assumption_set_id'],data['include_shot'])


def sensitivity(data,owner,root=None):
    s=select(data,owner,root)
    if s['observation_mode']=='full_observation':
        raise ValueError('Visibility scenarios require a partial snapshot; exclude observations explicitly first')
    results={name:compute(s,name,data['include_shot']) for name in SCENARIOS}
    candidate_ids={v['candidate_set_id'] for v in results.values()}
    if len(candidate_ids)!=1:
        raise ValueError('Sensitivity must compare the same visible candidate set')
    return dict(schema_version='visibility-sensitivity-1',video_id=s['video_id'],revision_id=s['revision_id'],snapshot_id=s['snapshot_id'],frame_index=s['frame_index'],
        visibility_scope_id=s['visibility_scope_id'],candidate_set_id=next(iter(candidate_ids)),scenario_model_version=SCENARIO_VERSION,q2_model_version=PARTIAL_VERSION,
        scenarios=results,**compare(results,data['assumption_set_id']),limitations=s['limitations'])
