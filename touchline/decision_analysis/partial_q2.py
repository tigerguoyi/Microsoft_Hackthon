"""Independent conditional two-step evaluator. Never invokes full Q2 on partial input.

Uses the versioned tactical probability functions as assumptions and the frozen xT tail.
No training, fake full-state schema, unseen real identities or future video frames.
"""
import copy
import math
from .partial_candidates import generate
from .tactical_rules import FEATURES, CONFIG, clip, sigmoid, tactical_probabilities

VERSION = 'partial-two-step-q2-1'


def geometry(s, a):
    actor = next(p for p in s['players'] if p['id'] == s['actor']); source=s['ball']; target=a['target']
    opponents=[p for p in s['players'] if p['team'] != s['team']]; field=[p for p in opponents if p['position'] != 'GK']
    keeper=next((p for p in opponents if p['position']=='GK'),None)
    length=math.dist(source,target); dx=target[0]-source[0];dy=target[1]-source[1]
    d=s['direction'] if s['team']==s['origin_team'] else -s['direction'];goal=[105 if d==1 else 0,34]
    def pressure(point):
        return s['background_pressure']+sum(math.exp(-math.dist(point,[p['x'],p['y']])/3) for p in field)
    nearest=min(opponents,key=lambda p:math.dist(source,[p['x'],p['y']]),default=None)
    nd=math.dist(source,[nearest['x'],nearest['y']]) if nearest else None
    closing=((nearest['vx']-actor['vx'])*(source[0]-nearest['x'])+(nearest['vy']-actor['vy'])*(source[1]-nearest['y']))/max(.01,nd) if nearest else 0.
    risks=[];blockers=0.
    for p in field:
        u=clip(((p['x']-source[0])*dx+(p['y']-source[1])*dy)/max(.01,length*length),.05,.95)
        point=[source[0]+u*dx,source[1]+u*dy];gap=math.dist(point,[p['x'],p['y']]);margin=.3+2*gap/(7.2+math.hypot(p['vx'],p['vy']))-u*a['duration']
        risks.append((math.exp(-gap/4)*sigmoid(-margin),margin,p['id'],point));blockers+=math.exp(-gap/1.8)
    risks.sort(reverse=True); receiver=next((p for p in s['players'] if p['id']==a['recipient']),actor)
    receiver_nearest=min((math.dist([receiver['x'],receiver['y']],[p['x'],p['y']]) for p in opponents),default=None)
    gd=math.dist(source,goal);gx=abs(goal[0]-source[0]);angle=abs(math.atan2(37.66-source[1],gx+.1)-math.atan2(30.34-source[1],gx+.1))
    cover=0.
    if keeper:
        u=clip(((keeper['x']-source[0])*(goal[0]-source[0])+(keeper['y']-source[1])*(34-source[1]))/max(.01,gd*gd),0,1)
        gap=math.dist([keeper['x'],keeper['y']],[source[0]+u*(goal[0]-source[0]),source[1]+u*(34-source[1])]);cover=math.exp(-gap/1.5)*math.exp(-math.dist(source,[keeper['x'],keeper['y']])/12)
    # Unknown entries are kept null in evidence. The probability formulas below do not
    # consume nearest distance, keeper depth for pass/carry, or missing match context.
    f=[actor['x'] if d==1 else 105-actor['x'],actor['y'],actor['vx']*d,actor['vy'],None,length,dx*d,dy,a['duration'],pressure(source),pressure(target),nd,closing,
       sum(r[0] for r in risks)+s['background_pressure'],risks[0][1] if risks else None,gd,angle,blockers,
       abs(keeper['y']-34) if keeper else None,math.hypot(receiver['vx'],receiver['vy']),1.,1.,None,None,None,receiver_nearest,1.,abs(goal[0]-keeper['x']) if keeper else None,cover if keeper else None,0.]
    defender=risks[0][2] if risks else nearest['id'] if nearest else None
    point=risks[0][3] if risks else target
    return f,defender,point


def successor(s,a,outcome,defender,loss_point):
    ns=copy.deepcopy(s);dt=a['duration']
    for p in ns['players']:
        p.update(x=clip(p['x']+p['vx']*dt,0,105),y=clip(p['y']+p['vy']*dt,0,68))
    if outcome=='success':
        actor=a['recipient'];point=a['target'];team=s['team']
    else:
        actor=defender;point=loss_point;team='AWAY' if s['team']=='HOME' else 'HOME'
        if outcome in ('saved','off_target'):
            keeper=next((p for p in ns['players'] if p['team']==team and p['position']=='GK'),None)
            if keeper:
                actor=keeper['id'];point=[keeper['x'],keeper['y']]
    if actor is None:
        return None  # No invented real controller; caller uses explicit turnover tail.
    for p in ns['players']:
        if p['id']==actor:p.update(x=point[0],y=point[1])
    ns.update(actor=actor,team=team,ball=list(point),t_ms=s['t_ms']+dt*1000)
    return ns


def tail(s,xt):
    d=s['direction'] if s['team']==s['origin_team'] else -s['direction'];x=s['ball'][0] if d==1 else 105-s['ball'][0]
    i=min(7,max(0,int(s['ball'][1]/68*8)))*12+min(11,max(0,int(x/105*12)))
    return float(xt[i])


def explanation(a, f):
    receiver = 'unknown' if f[25] is None else f'{f[25]:.1f} m'
    if a['kind']=='pass':
        return (f"Pass {f[5]:.1f} m to {a['recipient']}; forward change {f[6]:+.1f} m. Receiver's nearest modelled opponent: {receiver}.",
                f"Modelled lane pressure {f[13]:.2f}, receiving pressure {f[10]:.2f}. Offside and unobserved defense remain conditional.")
    if a['kind']=='carry':
        return (f"Move {f[6]:.1f} m forward over {a['duration']:.1f} s, then choose again. Modelled target pressure {f[10]:.2f}.",
                f"Start pressure {f[9]:.2f}, closing-speed estimate {f[12]:.1f} m/s; unknown velocity and unseen defenders depend on the stated assumptions.")
    return (f"Shot from {f[15]:.1f} m with geometric goal angle {math.degrees(f[16]):.1f} degrees.",
            f"Modelled blocking index {f[17]:.2f}; goalkeeper coverage may be hypothetical. This is not calibrated real-video xG.")


def evaluate(s,xt,depth=2,include_shot=False):
    rows=[]
    for a in generate(s,include_shot):
        if not a['supported']:
            rows.append(dict(**a,q=None));continue
        f,defender,point=geometry(s,a)
        if a['kind']=='shot' and f[28] is None:
            rows.append(dict(**{**a,'supported':False,'reason':'Keeper coverage unknown'},q=None));continue
        probs=tactical_probabilities(f,a['kind']);benefit=risk=immediate=0.
        for outcome,p in probs.items():
            if outcome=='goal':immediate+=p;continue
            ns=successor(s,a,outcome,defender,point)
            if ns is None:
                # Explicit restart/turnover tail at the failure point; not a recovered player.
                other='AWAY' if s['team']=='HOME' else 'HOME'
                v=tail({**s,'team':other,'ball':point},xt);same=False
            else:
                v=tail(ns,xt) if depth==1 else max((r['q'] for r in evaluate(ns,xt,depth-1,include_shot) if r.get('q') is not None),default=0.)
                same=ns['team']==s['team']
            c=p*math.exp(-a['duration']/120)*v
            if same:benefit+=c
            else:risk+=c
        opportunity,main_risk=explanation(a,f)
        rows.append(dict(**a,q=immediate+benefit-risk,immediate=immediate,continuation=benefit,risk=risk,
            probabilities=probs,features=dict(zip(FEATURES,f)),defender=defender,failure_target=point,
            opportunity=opportunity,main_risk=main_risk))
    return sorted(rows,key=lambda r:r['q'] if r['q'] is not None else -math.inf,reverse=True)
