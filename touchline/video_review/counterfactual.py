"""Same motion kernel; private partial binding and explicit hypothetical provenance."""
import copy
from .analysis import analyze
from .storage import digest
from decision_analysis.visibility_scenarios import state_for
from decision_analysis.motion import simulate_motion


def bound(data,owner,root=None):
    if set(data)!={'selection','snapshot_id','candidate_set_id','analysis_id','action_id'}:
        raise ValueError('Expected bound selection, snapshot, candidate, analysis and action IDs')
    result=analyze(data['selection'],owner,root)
    for k in ('snapshot_id','candidate_set_id','analysis_id'):
        if data[k]!=result.get(k):raise ValueError('Stale or mismatched '+k)
    candidate=next((c for c in result['ranking'] if c['action_id']==data['action_id'] and c['supported']),None)
    if candidate is None:raise ValueError('Action not supported in this exact candidate set and scenario')
    return result,candidate


def simulate(data,owner,root=None):
    result,candidate=bound(data,owner,root);s=result['snapshot']
    state,assumptions=state_for(s,'observed_only' if result['assumption_set_id']=='full' else result['assumption_set_id'],data['selection']['include_shot'])
    frame=dict(t_ms=s['timestamp_ms'],ball=[*state['ball'],0.,0.,0.,0.],players=[[p['id'],p['x'],p['y'],p['vx'],p['vy']] for p in state['players']])
    metadata=dict(players=[dict(player_id=p['id'],team_id=p['team'],position=p['position'] or 'OUTFIELD') for p in state['players']])
    trace=simulate_motion(frame,metadata,s['ball_carrier_id'],candidate,candidate['action_id'])
    binding={k:result[k] for k in ('snapshot_id','video_id','revision_id','frame_index','candidate_set_id','analysis_id','visibility_scope_id','assumption_set_id','observation_mode','scenario_model_version','q2_model_version')}
    trace.update(**binding,action_id=candidate['action_id'],action_type=candidate['action_type'],source_type='counterfactual_hypothesis',
        evidence_id='video-counterfactual:'+digest([binding,candidate['action_id']]),unknown_defender_count=assumptions['unknown_defender_count'],
        hypothetical_defender_count=assumptions['hypothetical_defender_count'],hypothetical_player_ids=[p['id'] for p in assumptions['hypothetical_players']],
        limitations=s['limitations'],main_risk=candidate['main_risk'],not_observed_future=True,ranking_unchanged=True)
    trace['assumptions'] += ['Scenario '+result['assumption_set_id']+'; virtual players are not video detections.']
    return trace


def compact(trace):
    result=copy.deepcopy(trace)
    result['cases']=[]
    for case in result.pop('scenarios'):
        case.pop('frames');case['scenario_id']=case.pop('id')
        case.update(action_id=trace['action_id'],action_type=trace['action_type'],candidate_set_id=trace['candidate_set_id'],
            evidence_id=trace['evidence_id']+':'+case['scenario_id'],source_type='counterfactual_hypothesis',main_risk=trace['main_risk'],assumptions=trace['assumptions'],limitations=trace['limitations'])
        result['cases'].append(case)
    result.update(counterfactual_supported=True,rollout_supported=True)
    return result
