"""Adapter for the existing four roles, Responses transport, budgets and Reviewer.

It supplies independent video evidence, never masquerades as a synthetic contract.
"""
import copy
from .analysis import analyze,sensitivity,compute
from .counterfactual import simulate,compact
from .storage import digest
from decision_analysis.visibility_scenarios import SCENARIOS


class VideoEvidenceAdapter:
    def __init__(self,selection,owner,root=None):
        self.selection=copy.deepcopy(selection);self.owner=owner;self.root=root;self.result=analyze(selection,owner,root)
        if self.result['level']<2 or not self.result['ranking']:raise ValueError('Candidate discovery only; configure verified conditional ranking before Agent Q&A')
        self.context={k:self.result[k] for k in ('video_id','revision_id','frame_index','visibility_scope_id','assumption_set_id','observation_mode','q2_model_version','scenario_model_version')}
        self.context['source_type']='real_video'
        self.surface=self._surface();self.document=dict(snapshot=self.surface['snapshot']);self.metadata=self.surface['metadata']

    def validate(self):
        current=analyze(self.selection,self.owner,self.root)
        if current['analysis_id']!=self.result['analysis_id']:raise ValueError('Video evidence expired; recompute after edits or scope changes')

    def _surface(self):
        r=self.result;s=r['snapshot'];candidates=[];evidence={}
        for c in r['ranking']:
            candidates.append(dict(action_id=c['action_id'],type=c['action_type'],eligible=True,rank=c['rank'],opportunity=c['opportunity'],main_risk=c['main_risk'],
                evidence_ids=[c['evidence_id']],assumptions=s['limitations']+[str(r['assumptions'])],counterfactual_supported=True,rollout_supported=False,
                q1=None,q2=c['q'],softmax_weight=c['softmax_weight'],relative_score=c['relative_score'],outcome_probabilities=c['probabilities'],
                decomposition={k:c.get(k) for k in ('immediate','continuation','risk')},features=c['features'],judgment={'conditional':True}))
            evidence[c['evidence_id']]=dict(kind='model_derived_conditional',value={k:c[k] for k in ('action_id','rank','opportunity','main_risk','features')},binding=self.context)
        snap=dict(snapshot_id=s['snapshot_id'],frame=dict(players=[[p['player_id'],*p['pitch'],*(p['velocity'] or [0,0])] for p in s['observed_players']],
            period=1,t_ms=s['timestamp_ms'],in_play=True,ball_owner_id=s['ball_carrier_id']))
        metadata=dict(players=[dict(player_id=p['player_id'],team_id=p['team_id'],name=p['name'] or p['player_id'],position=p['position']) for p in s['observed_players']])
        return dict(status='ready',snapshot_id=s['snapshot_id'],data_version=s['revision_id'],candidate_set_id=r['candidate_set_id'],candidates=candidates,evidence=evidence,
            limitations=s['limitations'],model=r['model'],assessment=dict(conditional=True,observation_context=self.context),action_conditions=dict(observed_counts=r['observed_counts'],missing_information=s['unknown_state']),
            snapshot=snap,metadata=metadata,request={},public={},private={},player_source_profile={})

    def tool(self,name,args):
        self.validate()
        if name=='compare_actions':
            if args:raise ValueError('No arguments accepted')
            return {k:self.surface[k] for k in ('candidates','evidence','model','assessment','action_conditions','limitations')}
        if name=='get_observation_evidence':
            if args:raise ValueError('No arguments accepted')
            s=self.result['snapshot'];eid='video-observations:'+s['snapshot_id']
            return dict(evidence_id=eid,source_type='human_confirmed_and_derived',binding=self.context,
                observed_players=s['observed_players'],unknown_state=s['unknown_state'],observation_quality=s['observation_quality'],limitations=s['limitations'])
        if name=='compare_visibility_scenarios':
            if args:raise ValueError('No arguments accepted')
            result=sensitivity(self.selection,self.owner,self.root)
            return dict(evidence_id='video-sensitivity:'+digest([self.context,result]),source_type='model_assumption_sensitivity',
                binding=self.context,rank_ranges=result['rank_ranges'],top_choice_stability=result['top_choice_stability'],ordering_changes=result['ordering_changes'],limitations=result['limitations'])
        if name=='simulate_action':
            if set(args)!={'action_id','assumption_set_id'}:raise ValueError('Expected action and explicit defensive scenario')
            scenario=args['assumption_set_id'];selection=copy.deepcopy(self.selection)
            if scenario!='same':
                if scenario not in SCENARIOS or self.result['observation_mode']=='full_observation':raise ValueError('Unsupported defensive scenario')
                selection['assumption_set_id']=scenario
            result=analyze(selection,self.owner,self.root)
            if result['candidate_set_id']!=self.result['candidate_set_id']:raise ValueError('Scenario changed visible candidates')
            value=compact(simulate(dict(selection=selection,snapshot_id=result['snapshot_id'],candidate_set_id=result['candidate_set_id'],analysis_id=result['analysis_id'],action_id=args['action_id']),self.owner,self.root))
            return value
        raise ValueError('Unknown video evidence tool')


def run(data,owner,config,root=None,transport=None):
    from decision.agents import Team,numeric_claims
    if set(data)!={'selection','snapshot_id','candidate_set_id','analysis_id','question','mode','language'}:
        raise ValueError('Expected bound video Agent request')
    adapter=VideoEvidenceAdapter(data['selection'],owner,root)
    for key in ('snapshot_id','candidate_set_id','analysis_id'):
        if data[key]!=adapter.result[key]:raise ValueError('Stale Agent '+key)
    if data['mode'] not in ('fan','analyst') or data['language'] not in ('en','zh') or not isinstance(data['question'],str) or not 1<=len(data['question'].strip())<=1000:
        raise ValueError('Invalid audience/language/question')
    if not config.get('api_key') or not config.get('model'):
        return dict(status='model_unavailable',answer=None,trace=[],candidate_set_id=adapter.result['candidate_set_id'],context=adapter.context,limitations=adapter.result['limitations'])
    team=Team(adapter.document,adapter.metadata,data['question'],data['mode'],config,transport,data['language'],evidence_adapter=adapter)
    result=team.run();adapter.validate()
    refs=(result.get('final') or {}).get('evidence_ids',[])
    claims=numeric_claims(result.get('answer'))
    limitations=list(adapter.result['limitations'])
    if claims:limitations.append('Agent numerical/probability claim withheld; conditional utilities are not calibrated probabilities.')
    return dict(status='partial' if claims else result['status'],answer=None if claims else result.get('answer'),candidate_set_id=adapter.result['candidate_set_id'],context=adapter.context,
        cited_evidence={k:team.registry[k] for k in refs if k in team.registry},trace=result['trace'],agent_outputs=result['agent_outputs'],
        tool_receipts=team.simulation_receipts,limitations=limitations)
