"""Real geometry/Q2/motion; only language transport and decoder-unit fixtures mocked."""
import copy
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from video_review import storage,service
from video_review.project import confirm,snapshot
from video_review.analysis import analyze,sensitivity,select
from video_review.counterfactual import simulate
from video_review.agents import VideoEvidenceAdapter
from decision_analysis.partial_candidates import generate
from decision_analysis.partial_q2 import successor
from decision_analysis.visibility_scenarios import SCENARIOS,state_for
from decision.agents import Team,ModelFailure


def draft_for(video_id,teammates=4):
    points=[(50,34),(60,20),(60,45),(40,25),(40,45)][:teammates+1]
    players=[dict(player_id='T'+str(i+1).zfill(2),track_id=i+17,team_id='HOME',image=[x/105,y/68],position=None,name=None,jersey_number=None,velocity=None,confidence=1.,human_verified=True,identity_status='confirmed',observation_status='visible') for i,(x,y) in enumerate(points)]
    f=dict(timestamp_ms=0,actor_id='T01',possession_team='HOME',attack_direction='positive_x',ball_image=[50/105,34/68],players=players,
        landmarks=[dict(image=[x,y],pitch=[105*x,68*y]) for x,y in [(0,0),(1,0),(1,1),(0,1)]],confirmed={k:True for k in ('calibration','direction','possession','ground_ball')},unknown_opponent_count=None,coverage_complete=False)
    return dict(video_id=video_id,parent_revision_id=None,rights_confirmed=True,frames=[f])


class VideoTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.owner='private-owner';self.vid='a'*32
        storage.write(storage.folder(self.vid,self.root)/'asset.json',dict(video_id=self.vid,owner=self.owner,latest_revision_id=None,duration_ms=2000,sha256='test-asset',bytes=48,created_at=0))
        self.draft=draft_for(self.vid);self.record=confirm(self.vid,self.draft,self.owner,self.root)
        self.selection=dict(video_id=self.vid,revision_id=self.record['revision_id'],frame_index=0,visibility_scope='verified',selected_player_ids=None,assumption_set_id='moderate_pressure_v1',include_shot=False)

    def tearDown(self):self.tmp.cleanup()
    def analysis(self,**changes):return analyze({**self.selection,**changes},self.owner,self.root)

    def test_four_teammates_produce_four_passes_and_three_carries(self):
        r=self.analysis();self.assertEqual(r['level'],2);self.assertEqual(len(r['candidate_actions']),7)
        self.assertEqual(sum(a['action_type']=='pass' for a in r['candidate_actions']),4)
        self.assertNotIn('shot:goal',[a['action_id'] for a in r['candidate_actions']])
        self.assertEqual(r['observed_counts']['visible_defenders'],0)
        self.assertEqual(r['missing_information']['unknown_defender_count'],'unknown')

    def test_two_teammates_generate_five_dynamic_actions(self):
        r=self.analysis(visibility_scope='custom',selected_player_ids=['T01','T02','T03'])
        self.assertEqual(len(r['candidate_actions']),5);self.assertEqual(r['observed_counts']['available_teammates'],2)

    def test_observed_only_is_discovery_not_zero_defense_ranking(self):
        r=self.analysis(assumption_set_id='observed_only');self.assertEqual(r['level'],1);self.assertEqual(r['ranking'],[])
        self.assertFalse(r['diagnostic']['ranking_available']);self.assertEqual(r['diagnostic']['nearest_visible_defender'],'unknown')

    def test_quality_failures_degrade_instead_of_fabricating_scores(self):
        for mutate in [lambda f:f.update(attack_direction=None),lambda f:f.update(actor_id=None),lambda f:f.update(ball_image=None),lambda f:f['confirmed'].update(calibration=False),lambda f:f.update(landmarks=[]),lambda f:f['players'][0].update(human_verified=False)]:
            draft=copy.deepcopy(self.draft);draft['parent_revision_id']=storage.asset(self.vid,self.owner,self.root)['latest_revision_id'];mutate(draft['frames'][0])
            record=confirm(self.vid,draft,self.owner,self.root)
            s=snapshot(record,0)
            self.assertFalse(s['observation_quality']['ready'])
        self.selection['revision_id']=record['revision_id']
        r=self.analysis(visibility_scope='custom',selected_player_ids=['T02']);self.assertEqual(r['level'],1);self.assertEqual(r['ranking'],[])

    def test_identity_team_jersey_and_human_quality_rules(self):
        s=select(self.selection,self.owner,self.root);state,_=state_for(s,'moderate_pressure_v1')
        for a in generate(state):
            if a['kind']=='pass':
                p=next(p for p in state['players'] if p['id']==a['recipient']);self.assertEqual(p['team'],state['team']);self.assertNotEqual(p['id'],state['actor']);self.assertFalse(p['hypothetical'])
        self.assertEqual(s['observed_players'][0]['track_id'],17);self.assertIsNone(s['observed_players'][0]['jersey_number'])
        self.assertIsNone(s['observed_players'][0]['velocity']);self.assertEqual(s['unknown_state']['goalkeeper'],'unknown');self.assertEqual(s['unknown_state']['offside_line'],'unknown')

    def test_scope_changes_bind_candidate_set_and_keep_exclusions_unknown(self):
        a=self.analysis();b=self.analysis(visibility_scope='custom',selected_player_ids=['T01','T02'])
        self.assertNotEqual(a['candidate_set_id'],b['candidate_set_id']);self.assertNotEqual(a['snapshot_id'],b['snapshot_id'])
        self.assertIn('T03',b['snapshot']['unknown_state']['excluded_ids'])
        with self.assertRaises(ValueError):self.analysis(visibility_scope='custom',selected_player_ids=['T99'])

    def test_scenario_state_is_deterministic_bounded_and_distinct_from_observations(self):
        s=select(self.selection,self.owner,self.root);original=copy.deepcopy(s)
        for scenario in SCENARIOS:
            a,assumptions=state_for(s,scenario);self.assertEqual((a,assumptions),state_for(s,scenario));self.assertEqual(s,original)
            virtual=assumptions['hypothetical_players'];self.assertGreater(len(virtual),0);self.assertLessEqual(len(virtual),11)
            for p in virtual:self.assertTrue(p['hypothetical']);self.assertTrue(0<=p['x']<=105 and 0<=p['y']<=68)
            self.assertEqual({p['id'] for p in a['players'] if not p['hypothetical']},{p['player_id'] for p in s['observed_players']})

    def test_two_step_never_recovers_unobserved_real_identities(self):
        s=select(self.selection,self.owner,self.root);state,_=state_for(s,'high_pressure_v1');before={p['id'] for p in state['players']}
        for a in generate(state):
            ns=successor(state,a,'success','hyp:1',a['target'])
            self.assertEqual({p['id'] for p in ns['players']},before)
            for b in generate(ns):
                if b['kind']=='pass':self.assertIn(b['recipient'],before)
            ns=successor(state,a,'loss','hyp:1',a['target']);self.assertEqual({p['id'] for p in ns['players']},before)
        self.assertEqual(len(before),8)  # Five observed + three explicitly hypothetical, not 22.

    def test_carry_directions_follow_attack_not_camera(self):
        s=select(self.selection,self.owner,self.root);s['attack_direction']='negative_x';state,_=state_for(s,'low_pressure_v1');rows={a['key']:a for a in generate(state)}
        self.assertLess(rows['carry:forward']['target'][0],50);self.assertGreater(rows['carry:left']['target'][1],34)

    def test_softmax_sums_ranks_and_unsupported_denominator(self):
        rows=self.analysis()['ranking'];self.assertAlmostEqual(sum(r['relative_score'] for r in rows),100)
        self.assertTrue(all(0<=r['relative_score']<=100 for r in rows));self.assertEqual([r['rank'] for r in rows],list(range(1,len(rows)+1)))
        self.assertEqual(sorted(rows,key=lambda r:r['relative_score'],reverse=True),rows)
        self.assertTrue(all(r['features']['keeper_depth'] is None and r['features']['ball_speed'] is None for r in rows))

    def test_explanations_use_current_action_geometry_and_keep_assumptions_explicit(self):
        rows=self.analysis()['ranking'];p=next(r for r in rows if r['action_type']=='pass');c=next(r for r in rows if r['action_type']=='carry')
        self.assertIn(p['recipient'],p['opportunity']);self.assertIn('modelled',p['opportunity']);self.assertIn('conditional',p['main_risk'])
        self.assertNotEqual(p['opportunity'],c['opportunity']);self.assertIn('stated assumptions',c['main_risk'])

    def test_sensitivity_recomputes_values_and_actual_top_choice_changes(self):
        result=sensitivity(self.selection,self.owner,self.root);self.assertFalse(result['top_choice_stability']['stable'])
        ids={r['candidate_set_id'] for r in result['scenarios'].values()};self.assertEqual(len(ids),1)
        q=[{r['action_id']:r['q'] for r in v['ranking']} for v in result['scenarios'].values()];self.assertNotEqual(q[0],q[-1]);self.assertTrue(result['ordering_changes'])
        self.assertEqual(result,sensitivity(self.selection,self.owner,self.root))

    def test_counterfactual_uses_bound_action_and_actual_assumed_defense(self):
        for scenario in ('low_pressure_v1','high_pressure_v1'):
            r=self.analysis(assumption_set_id=scenario);selection={**self.selection,'assumption_set_id':scenario};body=dict(selection=selection,**{k:r[k] for k in ('snapshot_id','candidate_set_id','analysis_id')},action_id='carry:forward')
            trace=simulate(body,self.owner,self.root);self.assertEqual(trace['assumption_set_id'],scenario);self.assertTrue(trace['not_observed_future']);self.assertTrue(trace['ranking_unchanged']);self.assertEqual(len(trace['scenarios']),4)
            self.assertEqual(len([p for p in trace['scenarios'][0]['frames'][0]['players'] if p[0].startswith('hyp:')]),trace['hypothetical_defender_count'])
            for key in ('snapshot_id','candidate_set_id','analysis_id'):
                with self.assertRaises(ValueError):simulate({**body,key:'stale'},self.owner,self.root)
            with self.assertRaises(ValueError):simulate({**body,'action_id':'pass:T99'},self.owner,self.root)

    def test_revision_edit_invalidates_all_older_context_and_agent_tools(self):
        adapter=VideoEvidenceAdapter(self.selection,self.owner,self.root);new=copy.deepcopy(self.draft);new['parent_revision_id']=self.record['revision_id'];new['frames'][0]['players'][1]['image'][0]+=.01
        updated=confirm(self.vid,new,self.owner,self.root);self.assertNotEqual(updated['revision_id'],self.record['revision_id'])
        with self.assertRaises(ValueError):self.analysis()
        with self.assertRaises(ValueError):adapter.tool('compare_actions',{})
        with self.assertRaises(ValueError):confirm(self.vid,new,self.owner,self.root)
        old=storage.revision(self.vid,self.record['revision_id'],self.owner,self.root,current=False);self.assertEqual(old,self.record)

    def test_immutable_clock_order_and_unknown_id_handling(self):
        new=copy.deepcopy(self.draft);new['parent_revision_id']=self.record['revision_id'];new['frames'].append(copy.deepcopy(new['frames'][0]));new['frames'][0]['timestamp_ms']=1000
        record=confirm(self.vid,new,self.owner,self.root);self.assertEqual(record['annotation']['frames'][0]['timestamp_ms'],0);self.assertEqual(record['frames'][0]['timestamp_ms'],0)

    def test_owner_isolation_and_path_traversal(self):
        with self.assertRaises(FileNotFoundError):storage.asset(self.vid,'other-owner',self.root)
        for value in ('../x','a'*31,'a'*32+'/x'):
            with self.assertRaises(ValueError):storage.folder(value,self.root)

    def test_full_mode_cannot_be_selected_for_partial_and_no_fake_keepership(self):
        with self.assertRaises(ValueError):self.analysis(assumption_set_id='full')
        r=self.analysis(include_shot=True);self.assertTrue(any(p['position']=='GK' and p['hypothetical'] for p in r['assumptions']['hypothetical_players']))
        self.assertEqual(r['missing_information']['goalkeeper'],'unknown')
        self.assertTrue(all(p['position'] is None for p in r['snapshot']['observed_players']))

    def test_genuinely_complete_video_uses_unchanged_full_q2_and_same_xT(self):
        from video_review.analysis import full_rows,frozen_model
        source=Path(__file__).resolve().parents[1]/'data/league/matches/PL26-W01-MCI-CHE'
        with (source/'decisions.jsonl').open() as stream:raw=json.loads(stream.readline())['snapshot']
        metadata=json.loads((source/'metadata.json').read_text())
        players={p['player_id']:p for p in metadata['players']};names={p[0]:'T'+str(i+1).zfill(2) for i,p in enumerate(raw['players'])}
        new=copy.deepcopy(self.draft);new['parent_revision_id']=self.record['revision_id'];f=new['frames'][0];f['players']=[]
        for p in raw['players']:
            f['players'].append(dict(player_id=names[p[0]],track_id=None,team_id=players[p[0]]['team_id'],image=[p[1]/105,p[2]/68],position='GK' if players[p[0]]['position']=='GK' else 'OUTFIELD',name=None,jersey_number=None,velocity=p[3:5],confidence=1.,human_verified=True,identity_status='confirmed',observation_status='visible'))
        f.update(actor_id=names[raw['ball_owner_id']],possession_team=players[raw['ball_owner_id']]['team_id'],ball_image=[raw['ball'][0]/105,raw['ball'][1]/68],coverage_complete=True,unknown_opponent_count=0)
        record=confirm(self.vid,new,self.owner,self.root);selected={**self.selection,'revision_id':record['revision_id'],'assumption_set_id':'full'}
        result=analyze(selected,self.owner,self.root);self.assertEqual(result['level'],3);self.assertEqual(result['observation_mode'],'full_observation')
        state,_=state_for(result['snapshot'],'observed_only');expected=[a for a in full_rows(state,frozen_model()['xt']) if a['supported']]
        self.assertEqual([(a['action_id'],a['q']) for a in result['ranking']],[(a['key'],a['q']) for a in expected])
        self.assertEqual(result['missing_information']['unknown_defender_count'],0)

    def test_video_agent_tools_share_four_role_registry_and_explicit_scenarios(self):
        adapter=VideoEvidenceAdapter(self.selection,self.owner,self.root)
        team=Team(adapter.document,adapter.metadata,'Would a defender change it?','analyst',{},evidence_adapter=adapter)
        evidence=team.execute('attack','get_observation_evidence',{});self.assertIn(evidence['evidence_id'],team.registry)
        compared=team.execute('attack','compare_visibility_scenarios',{});self.assertFalse(compared['top_choice_stability']['stable'])
        value=team.execute('defense','simulate_action',{'action_id':'carry:left','assumption_set_id':'high_pressure_v1'})
        self.assertNotIn('frames',json.dumps(value));self.assertEqual(value['assumption_set_id'],'high_pressure_v1')
        receipt=team.execute('reviewer','check_evidence',{})['counterfactual_tool_receipts'][0]
        for key in ('video_id','revision_id','frame_index','visibility_scope_id','assumption_set_id','candidate_set_id'):
            self.assertEqual(receipt[key],value[key])
        team.shared['defense']={'status':'complete'}
        good=dict(answer='Conditional hypothesis only.',action_id='carry:left',evidence_ids=[value['evidence_id']],caveats=[])
        team.validate_answer({**good,'verdict':'accept'},'reviewer')
        with self.assertRaises(ModelFailure):team.validate_answer({**good,'action_id':'carry:right'},'defense')

    def test_actual_four_role_orchestration_uses_video_tools_with_mock_language_transport_only(self):
        from test_agents import scripted_transport,CONFIG
        from video_review.agents import run
        adapter=VideoEvidenceAdapter(self.selection,self.owner,self.root);base,requests=scripted_transport('carry:forward')
        def language(payload):
            response=base(payload)
            for item in response['output']:
                if item.get('type')=='function_call' and item['name']=='simulate_action':
                    args=json.loads(item['arguments']);args['assumption_set_id']='high_pressure_v1';item['arguments']=json.dumps(args)
            return response
        r=adapter.result;data=dict(selection=self.selection,**{k:r[k] for k in ('snapshot_id','candidate_set_id','analysis_id')},question='What if a defender closes?',mode='analyst',language='en')
        result=run(data,self.owner,CONFIG,self.root,language)
        self.assertEqual(result['status'],'complete',result)
        self.assertEqual(result['tool_receipts'][0]['assumption_set_id'],'high_pressure_v1')
        self.assertEqual([t['target'] for t in result['trace'] if t['event']=='handoff'],['attack','defense','reviewer'])
        self.assertNotIn(CONFIG['api_key'],json.dumps(result))

    def test_future_frame_edits_change_revision_but_not_current_numeric_evaluation(self):
        before=self.analysis();draft=copy.deepcopy(self.draft);draft['parent_revision_id']=self.record['revision_id']
        later=copy.deepcopy(draft['frames'][0]);later['timestamp_ms']=1000;later['players'][1]['image']=[.9,.9];draft['frames'].append(later)
        record=confirm(self.vid,draft,self.owner,self.root)
        after=analyze({**self.selection,'revision_id':record['revision_id']},self.owner,self.root)
        self.assertNotEqual(before['analysis_id'],after['analysis_id'])
        self.assertEqual([(r['action_id'],r['q'],r['features'],r['relative_score']) for r in before['ranking']],[(r['action_id'],r['q'],r['features'],r['relative_score']) for r in after['ranking']])

    def test_video_language_probability_claim_is_withheld_without_changing_ranking(self):
        from video_review.agents import run
        from test_agents import scripted_transport,CONFIG
        adapter=VideoEvidenceAdapter(self.selection,self.owner,self.root);original=copy.deepcopy(adapter.result['ranking']);base,_=scripted_transport('carry:forward')
        def language(payload):
            response=base(payload)
            for item in response['output']:
                if item.get('type')=='function_call' and item['name']=='simulate_action':
                    item['arguments']=json.dumps(dict(action_id='carry:forward',assumption_set_id='same'))
                if item.get('type')=='message':
                    answer=json.loads(item['content'][0]['text']);answer['answer']='Success chance is 90%.';item['content'][0]['text']=json.dumps(answer)
            return response
        r=adapter.result;data=dict(selection=self.selection,**{k:r[k] for k in ('snapshot_id','candidate_set_id','analysis_id')},question='Compare',mode='fan',language='en')
        result=run(data,self.owner,CONFIG,self.root,language)
        self.assertEqual(result['status'],'partial');self.assertIsNone(result['answer']);self.assertEqual(self.analysis()['ranking'],original)

    def test_upload_signature_size_decoder_and_cleanup(self):
        root=self.root/'uploads';media=b'\0\0\0\x18ftypisom'+b'0'*64
        details=dict(duration_ms=2000,decoder_verified=True,width=100,height=100,fps=25,frame_count=50)
        a=storage.upload(io.BytesIO(media),len(media),'video/mp4',self.owner,root,probe=lambda _:details)
        self.assertTrue(a['decoder_verified']);self.assertNotIn('owner',a)
        for size in (0,storage.MAX_BYTES+1):
            with self.assertRaises(ValueError):storage.upload(io.BytesIO(media),size,'video/mp4',self.owner,root)
        with self.assertRaises(ValueError):storage.upload(io.BytesIO(b'x'*80),80,'video/mp4',self.owner,root,probe=lambda _:details)
        with self.assertRaises(ValueError):storage.upload(io.BytesIO(media),len(media),'video/mp4',self.owner,root,probe=lambda _:(_ for _ in ()).throw(ValueError('Bad decode')))
        self.assertEqual(len(list(root.glob('*/asset.json'))),1)

    def test_public_intake_disabled_and_private_cookie_csrf_binding(self):
        class Handler:
            headers={'Host':'127.0.0.1:5555'};client_address=('127.0.0.1',0)
            def trusted(self):return True
        h=Handler()
        with patch.object(storage,'ROOT',self.root):
            self.assertTrue(service.enabled(h))
            with patch.dict(os.environ,{'WEBSITE_INSTANCE_ID':'azure'}):self.assertFalse(service.enabled(h))
            h.headers={'Host':'example.azurewebsites.net'};self.assertFalse(service.enabled(h))
            h.headers={'Host':'127.0.0.1:5555'};token,owner,csrf=service.session(h,True)
            h.headers['Cookie']='nextplay_video_session='+token
            self.assertEqual(service.session(h)[1],owner)
            with self.assertRaises(PermissionError):service.gate(h,True)
            h.headers['X-Video-CSRF']=csrf;self.assertEqual(service.gate(h,True),owner)

    def test_job_status_expires_and_ownership_checks_are_not_bypassed(self):
        from video_review.jobs import status
        jid='b'*32;storage.write(storage.folder(self.vid,self.root)/('job-'+jid+'.json'),dict(job_id=jid,video_id=self.vid,status='running',progress=.2,created_at=0))
        result=status(self.vid,jid,self.owner,self.root);self.assertEqual(result['status'],'failed')
        with self.assertRaises(FileNotFoundError):status(self.vid,jid,'other',self.root)
        with self.assertRaises(ValueError):status(self.vid,'../../media',self.owner,self.root)

    def test_contracts_compile_and_validate_computed_not_placeholder_payloads(self):
        import subprocess,shutil
        node=os.getenv('NODE_BINARY') or shutil.which('node')
        if not node:self.skipTest('Node unavailable for AJV validation')
        r=self.analysis();sens=sensitivity(self.selection,self.owner,self.root)
        body=dict(selection=self.selection,**{k:r[k] for k in ('snapshot_id','candidate_set_id','analysis_id')},action_id='carry:left')
        trace=simulate(body,self.owner,self.root)
        docs=[dict(kind='selection',value=self.selection),dict(kind='annotation',value=self.draft),dict(kind='snapshot',value=r['snapshot']),dict(kind='analysis_response',value=r),dict(kind='sensitivity_response',value=sens),dict(kind='counterfactual_request',value=body),dict(kind='counterfactual_response',value=trace)]
        command=[node,str(Path(__file__).resolve().parents[1]/'scripts_validate_video_contracts.mjs'),'--stdin']
        result=subprocess.run(command,input='\n'.join(json.dumps(x) for x in docs),capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        docs[0]['value']={**self.selection,'include_shot':'true'}
        bad=subprocess.run(command,input=json.dumps(docs[0]),capture_output=True,text=True);self.assertNotEqual(bad.returncode,0)


if __name__=='__main__':unittest.main()
