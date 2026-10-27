"""Candidates from verified visible identities only, in both Q2 steps."""
import math

VERSION = 'visible-passes-three-carries-1'


def generate(state, include_shot=False):
    actor = next(p for p in state['players'] if p['id'] == state['actor'])
    source = state['ball']; d = state['direction'] if state['team'] == state['origin_team'] else -state['direction']
    actions = []
    for p in state['players']:
        if p['team'] != state['team'] or p['id'] == state['actor']:
            continue
        target = [p['x'] + .25 * p['vx'], p['y'] + .25 * p['vy']]
        length = math.dist(source, target)
        supported = length <= 35 and 0 <= target[0] <= 105 and 0 <= target[1] <= 68
        actions.append(dict(key='pass:' + p['id'], kind='pass', recipient=p['id'], target=target, duration=max(.05, length / 14),
            mode='ground', reachable=True, supported=supported, offside_status='unknown' if not state.get('complete') else 'checked_by_full_adapter',
            reason=None if supported else 'Partial model supports ground passes up to 35 m inside pitch'))
    for name, lateral in [('forward', 0), ('left', -4), ('right', 4)]:
        target = [actor['x'] + d * 6, actor['y'] + d * lateral]
        valid = 1 <= target[0] <= 104 and 1 <= target[1] <= 67
        actions.append(dict(key='carry:' + name, kind='carry', recipient=actor['id'], target=target, duration=2., mode='ground',
            reachable=True, supported=valid, offside_status='not_applicable', reason=None if valid else 'Carry target outside support'))
    if include_shot:
        goal = [105. if d == 1 else 0., 34.]
        keeper = any(p['team'] != state['team'] and p.get('position') == 'GK' for p in state['players'])
        valid = keeper and math.dist(source, goal) <= 40
        actions.append(dict(key='shot:goal', kind='shot', recipient=None, target=goal, duration=max(.4, math.dist(source, goal) / 24), mode='ordinary',
            reachable=True, supported=valid, offside_status='not_applicable', reason=None if valid else 'Conditional shot requires a declared keeper and range ≤40 m'))
    return actions
