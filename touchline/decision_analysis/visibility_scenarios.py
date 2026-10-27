"""Explicit reproducible virtual coverage, never detected players or percentiles."""
import copy
import math
from .tactical_rules import clip

VERSION = 'visibility-defense-1'
SCENARIOS = {'low_pressure_v1':dict(count=1, ahead=14., lateral=12., background=.05),
             'moderate_pressure_v1':dict(count=2, ahead=8., lateral=6., background=.15),
             'high_pressure_v1':dict(count=3, ahead=3., lateral=3., background=.35)}


def state_for(snapshot, scenario, include_shot=False):
    if scenario not in SCENARIOS and scenario != 'observed_only':
        raise ValueError('Unknown defensive assumption set')
    team = snapshot['possession_team']; d = 1 if snapshot['attack_direction'] == 'positive_x' else -1
    players = [dict(id=p['player_id'],team=p['team_id'],x=p['pitch'][0],y=p['pitch'][1],vx=(p['velocity'] or [0,0])[0],vy=(p['velocity'] or [0,0])[1],position=p['position'],hypothetical=False) for p in snapshot['observed_players']]
    observed = [p for p in players if p['team'] != team]
    unknown = snapshot['unknown_state']['unknown_defender_count']; available = 11 - len(observed)
    capacity = min(available, unknown) if type(unknown) is int else available
    config = SCENARIOS.get(scenario); hypothetical = []
    if config:
        n = min(config['count'], capacity)
        ball = snapshot['ball_position']
        for i in range(n):
            x = clip(ball[0] + d * (config['ahead'] + 2 * i), .5, 104.5)
            y = clip(ball[1] + (1 if i % 2 == 0 else -1) * config['lateral'], .5, 67.5)
            # Resolve collisions without moving any actual observation.
            for k in range(100):
                if all(math.dist([x,y],[p['x'],p['y']]) >= 1.5 for p in players + hypothetical):
                    break
                y = .5 + (y + 2.7) % 67
            else:
                raise ValueError('Unable to place a non-overlapping hypothetical defender')
            hypothetical.append(dict(id='hyp:' + str(i+1),team='AWAY' if team=='HOME' else 'HOME',x=x,y=y,vx=0.,vy=0.,position='OUTFIELD',hypothetical=True))
        if include_shot and not any(p['position'] == 'GK' for p in observed) and capacity > len(hypothetical):
            keeper=dict(id='hyp:keeper',team='AWAY' if team=='HOME' else 'HOME',x=103. if d==1 else 2.,y=34.,vx=0.,vy=0.,position='GK',hypothetical=True)
            while any(math.dist([keeper['x'],keeper['y']],[p['x'],p['y']])<1.5 for p in players+hypothetical):
                keeper['y'] = .5 + (keeper['y']+2.7)%67
            hypothetical.append(keeper)
    background = config['background'] if config and (unknown == 'unknown' or unknown > len(hypothetical)) else 0.
    result = dict(players=players+hypothetical,actor=snapshot['ball_carrier_id'],team=team,origin_team=team,direction=d,ball=list(snapshot['ball_position']),t_ms=snapshot['timestamp_ms'],
        complete=snapshot['observation_mode']=='full_observation',background_pressure=background)
    assumptions = dict(assumption_set_id=scenario,scenario_model_version=VERSION,hypothetical_players=copy.deepcopy(hypothetical),
        unknown_defender_count=unknown,hypothetical_defender_count=len(hypothetical),unmodelled_background_pressure=background,
        selected_parameters=copy.deepcopy(config),unknown_velocities='neutral_zero_prediction_only',
        note='A limited tested geometry, not all possible unseen defense or a calibrated risk percentile. Observed-only is diagnostic, not a proven lower bound.')
    return result, assumptions
