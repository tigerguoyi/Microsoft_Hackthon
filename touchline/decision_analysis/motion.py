"""Shared deterministic motion for full and explicitly hypothetical partial scenes.
The caller validates provenance and action binding; this kernel never invents identities.
"""
import copy
import math
from decision.rollout import advance, SCENARIOS, DT
from .pass_rollout import simulate as pass_simulate


def simulate_motion(frame, metadata, actor, row, action_id):
    teams={p['player_id']:p['team_id'] for p in metadata['players']}
    team=teams[actor];start=frame['ball'][:2];target=row['target']
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
    return result
