"""Explicit deterministic hypotheses for every ranked pass/carry/shot, not future observations."""
import copy
import math
from decision.rollout import advance, SCENARIOS, DT
from .pass_rollout import simulate as pass_simulate
from contracts import check_exchange
from .input_adapter import validate_request, adapt_snapshot
from .q2 import _scope


def validate_simulation_binding(request, public, private, snapshot, metadata,
                                action_id, expected_id, observation_context=None):
    """One gate for Lab and Agent. No state recovery or scoring happens here.

    Video/partial revisions require their own future adapter. They must never
    fall through into the complete synthetic-state model.
    """
    context = observation_context or {}
    if (not isinstance(context, dict) or set(context) - {'source_type', 'observation_mode', 'visibility_scope_id'}
            or context.get('source_type', 'synthetic_match') != 'synthetic_match'
            or context.get('observation_mode', 'full_observation') != 'full_observation'
            or context.get('visibility_scope_id', 'full_snapshot') != 'full_snapshot'):
        raise ValueError('Video revisions and partial defensive assumptions are not supported in Phase 1–3')
    validate_request(request)
    check_exchange(request, public, snapshot, metadata)
    if not 14 <= len(snapshot['frame']['players']) <= 22:
        raise ValueError('Full observation requires a complete tracking snapshot, not a partial observation')
    if expected_id != public['candidate_set_id']:
        raise ValueError('Stale candidate set')
    if (private.get('snapshot_id') != snapshot['snapshot_id']
            or private.get('candidate_set_id') != expected_id):
        raise ValueError('Private simulation state belongs to another snapshot or candidate set')
    candidates = [c for c in public['candidates'] if c['action_id'] == action_id]
    rows = [r for r in private.get('options', []) if r['key'] == action_id]
    if (len(candidates) != 1 or len(rows) != 1 or not candidates[0]['eligible']
            or candidates[0]['type'] not in ('pass', 'carry', 'shot')):
        raise ValueError('Unsupported or unknown counterfactual action')
    candidate, row = candidates[0], rows[0]
    # Rebuild only the existing standard template, not its Q value. An envelope
    # with the right IDs cannot smuggle a target/duration from another decision.
    state, functions, reverse = _scope(adapt_snapshot(snapshot, metadata))
    templates = []
    for option in functions['candidate_actions'](state):
        option = dict(option)
        option['recipient'] = reverse.get(option.get('recipient'), option.get('recipient'))
        if option['kind'] == 'pass':
            option['key'] = 'pass:' + option['recipient']
        if option['key'] == action_id:
            templates.append(option)
    if len(templates) != 1:
        raise ValueError('Action is not part of this snapshot template set')
    template = templates[0]
    if (not row.get('supported') or not template['supported'] or row['kind'] != candidate['type']
            or any(row.get(k) != template.get(k) for k in ('kind', 'recipient', 'target', 'mode', 'duration'))):
        raise ValueError('Counterfactual template disagrees with the bound snapshot')
    return candidate, row


def simulate(request, public, private, snapshot, metadata, action_id, expected_id, *, observation_context=None):
    candidate,row=validate_simulation_binding(request,public,private,snapshot,metadata,action_id,expected_id,observation_context)
    frame=snapshot['frame'];teams={p['player_id']:p['team_id'] for p in metadata['players']}
    actor=request['actor_id'];team=teams[actor];start=frame['ball'][:2];target=row['target']
    if row['kind']=='pass':
        result=pass_simulate(frame,metadata,action_id,analysis=dict(actor_id=actor,team_id=team,
            candidates=[dict(action_id=action_id,receiver_id=row['recipient'],start=start,target=target,feasible_by_rules=True)]))
        for scenario in result['scenarios']:
            for f in scenario['frames']:f['ball']=[*f['ball'],0.,0.,0.,0.]
            scenario['frames'][0]['ball']=copy.deepcopy(frame['ball'])
    else:
        result=dict(action_id=action_id,kind='counterfactual',source_t_ms=frame['t_ms'],horizon_s=4.,step_s=DT,scenarios=[],
            assumptions=['Four deterministic hypotheses, not outcome-probability samples.',
                'Movement uses 7.2 m/s and 3.5 m/s² caps; no collisions, fatigue or individual skill model.',
                'Carry retains ball until a defender reaches 1 m; shot uses a 24 m/s straight ground trajectory.',
                'Shot contact within 1 m blocks; goalkeeper contact within 1.5 m saves. No rebounds or aerial physics.',
                'These playback rules differ from Q2 branch probabilities and do not validate or change the ranking.'])
        for name,delay,error in SCENARIOS:
            players=copy.deepcopy(frame['players']);frames=[dict(elapsed_s=0.,players=copy.deepcopy(players),ball=copy.deepcopy(frame['ball']))]
            aimed=target[:];aimed[1]=max(0,min(68,aimed[1]+error));length=math.dist(start,aimed)
            duration=min(4.,row['duration'] if row['kind']=='carry' else max(.05,length/24))
            outcome='unresolved';owner=None
            for step in range(1,81):
                t=step*DT;old_actor=next(p for p in players if p[0]==actor)
                # Defender movement uses current information and the chosen template only.
                if row['kind']=='carry':ball=old_actor[1:3]
                else:ball=[start[j]+min(1,t/max(length/24,.05))*(aimed[j]-start[j]) for j in (0,1)]
                players=[advance(p,aimed if p[0]==actor else ball,
                    row['kind']=='carry' and p[0]==actor or teams[p[0]]!=team and t>delay) for p in players]
                if row['kind']=='carry':
                    carrier=next(p for p in players if p[0]==actor);ball=carrier[1:3]
                    defenders=sorted((math.dist(p[1:3],ball),p[0]) for p in players if teams[p[0]]!=team)
                    if defenders and defenders[0][0]<=1:outcome='intercepted';owner=defenders[0][1]
                    elif t+1e-9>=duration:outcome='retained';owner=actor
                else:
                    hits=[]
                    for p in players:
                        if teams[p[0]]==team:continue
                        meta=next(m for m in metadata['players'] if m['player_id']==p[0]);keeper=meta['position']=='GK'
                        if math.dist(p[1:3],ball)<=(1.5 if keeper else 1.):hits.append((math.dist(p[1:3],ball),p[0],keeper))
                    if hits:
                        _,owner,keeper=min(hits);outcome='saved' if keeper else 'blocked'
                    elif t+1e-9>=duration:
                        reached=t+1e-9>=length/24
                        outcome=('goal' if abs(ball[1]-34)<=3.66 else 'off_target') if reached else 'unresolved'
                frames.append(dict(elapsed_s=round(t,3),players=copy.deepcopy(players),ball=[*ball,0.,0.,0.,0.]))
                if outcome!='unresolved' or t+1e-9>=duration:break
            result['scenarios'].append(dict(id=name,reaction_s=delay,lateral_error_m=error,outcome=outcome,controller_id=owner,
                duration_s=frames[-1]['elapsed_s'],frames=frames))
        result['summary']='Deterministic short movement hypotheses; scenario counts are not probabilities.'
    period=next(p for p in metadata['periods'] if p['period']==snapshot['period'])
    remaining=max(0.,(period['start_ms']+period['duration_ms']-snapshot['t_ms'])/1000)
    for scenario in result['scenarios']:
        original=scenario['duration_s']
        scenario['frames']=[f for f in scenario['frames'] if f['elapsed_s']<=remaining+1e-9]
        if not scenario['frames']:
            scenario['frames']=[dict(elapsed_s=0.,players=copy.deepcopy(frame['players']),ball=copy.deepcopy(frame['ball']))]
        scenario['duration_s']=scenario['frames'][-1]['elapsed_s']
        if original>remaining:
            scenario['outcome']='period_end';scenario['controller_id']=None
    result['assumptions'].append('Playback is truncated at the current metadata period boundary.')
    result.update(schema_version='decision-counterfactual-1',snapshot_id=snapshot['snapshot_id'],data_version=snapshot['data_version'],
        candidate_set_id=public['candidate_set_id'],action_type=row['kind'],start=start,target=target,
        template_speed_mps=14. if row['kind']=='pass' else 24. if row['kind']=='shot' else None,
        ranking_unchanged=True,not_observed_future=True)
    return result
