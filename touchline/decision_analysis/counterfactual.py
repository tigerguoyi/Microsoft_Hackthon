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
    from .motion import simulate_motion
    frame=snapshot['frame'];start=frame['ball'][:2];target=row['target']
    result=simulate_motion(frame,metadata,request['actor_id'],row,action_id)
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
