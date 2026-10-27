"""Phase 1: the real full-state engine, mocked language transport only."""
import copy
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from decision.agents import Team, ModelFailure, run_team
from decision_analysis.counterfactual import simulate
from decision_analysis.service import Repository
from test_agents import CONFIG, scripted_transport

ROOT=Path(__file__).resolve().parents[1]


class AgentCounterfactualTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo=Repository();cls.match='PL26-W01-MCI-CHE'
        cls.record=next(iter(cls.repo.records(cls.match).values()))
        cls.snapshot=cls.record['snapshot'];cls.metadata=cls.repo.metadata(cls.match)
        cls.request=cls.repo.request_for(cls.snapshot);cls.document=cls.repo.document(cls.request)
        cls.public,cls.private=cls.repo.compare(cls.request)

    def team(self):
        return Team(copy.deepcopy(self.document),self.metadata,'Compare these choices','fan',CONFIG,
                    private=copy.deepcopy(self.private))

    def action(self,kind):
        return next(c['action_id'] for c in self.public['candidates'] if c['eligible'] and c['type']==kind)

    def test_pass_carry_shot_use_the_lab_engine_and_return_only_bound_summaries(self):
        for kind in ('pass','carry','shot'):
            team=self.team();aid=self.action(kind);before=copy.deepcopy(team.surface['public'])
            with patch('decision_analysis.counterfactual.simulate',wraps=simulate) as engine:
                value=team.execute('defense','simulate_action',{'action_id':aid})
                self.assertEqual(engine.call_count,1)
            full=simulate(self.request,self.public,self.private,self.snapshot,self.metadata,aid,self.public['candidate_set_id'])
            self.assertEqual(value['action_type'],kind);self.assertEqual(value['action_id'],aid)
            self.assertEqual(value['candidate_set_id'],self.public['candidate_set_id'])
            self.assertEqual([(c['scenario_id'],c['outcome']) for c in value['cases']],[(c['id'],c['outcome']) for c in full['scenarios']])
            for case in value['cases']:
                for key in ('action_id','action_type','scenario_id','candidate_set_id','outcome','main_risk','assumptions','limitations','evidence_id','source_type'):
                    self.assertIn(key,case)
                self.assertEqual(case['source_type'],'counterfactual_hypothesis');self.assertNotIn('frames',case)
            self.assertNotIn('frames',json.dumps(list(team.rollouts.values())))
            self.assertEqual(team.surface['public'],before)
            self.assertTrue(value['ranking_unchanged']);self.assertTrue(value['not_observed_future'])

    def test_all_three_action_types_complete_actual_four_role_tool_workflow(self):
        for kind in ('pass','carry','shot'):
            aid=self.action(kind);transport,requests=scripted_transport(aid)
            result=run_team(copy.deepcopy(self.document),self.metadata,'What if this action?', 'analyst',CONFIG,
                            transport,private=copy.deepcopy(self.private))
            self.assertEqual(result['status'],'complete',result)
            self.assertTrue(result['is_multi_agent'])
            self.assertTrue(any(t.get('tool')=='simulate_action' and t.get('arguments',{}).get('action_id')==aid for t in result['trace']))
            tool_results=[json.loads(x['output']) for p in requests for x in p['input'] if x.get('type')=='function_call_output']
            self.assertTrue(any(x.get('action_type')==kind and x.get('counterfactual_supported') for x in tool_results))
            self.assertFalse(any('frames' in x for x in tool_results))
            checked=next(x for x in tool_results if 'counterfactual_tool_receipts' in x)
            self.assertTrue(checked['checks']['same_snapshot']);self.assertTrue(checked['checks']['counterfactual_calls_recorded'])
            self.assertEqual(checked['counterfactual_tool_receipts'][0]['action_id'],aid)

    def test_forward_left_right_are_distinct_supported_carry_tools(self):
        team=self.team();ids=[]
        for name in ('forward','left','right'):
            value=team.execute('defense','simulate_action',{'action_id':'carry:'+name});ids.append(value['evidence_id'])
        self.assertEqual(len(set(ids)),3)

    def test_unknown_unsupported_and_wrong_bound_states_are_rejected(self):
        for aid in ('hold:1s','pass:H99','carry:invented'):
            with self.assertRaises(ValueError):self.team().execute('defense','simulate_action',{'action_id':aid})
        aid=self.action('carry')
        for mutate in [lambda t:t.surface['request'].update(t_ms=999),
                       lambda t:t.surface['public'].update(snapshot_id='0'*16),
                       lambda t:t.surface['private'].update(candidate_set_id='old'),
                       lambda t:t.surface['private'].update(snapshot_id='old'),
                       lambda t:next(r for r in t.surface['private']['options'] if r['key']==aid).update(target=[0.,0.])]:
            team=self.team();mutate(team)
            with self.assertRaises(ValueError):team.execute('defense','simulate_action',{'action_id':aid})

    def test_cache_is_bound_and_revalidated_instead_of_reusing_another_decision(self):
        team=self.team();aid=self.action('carry')
        with patch('decision_analysis.counterfactual.simulate',wraps=simulate) as engine:
            first=team.execute('defense','simulate_action',{'action_id':aid})
            second=team.execute('defense','simulate_action',{'action_id':aid})
            self.assertEqual(first,second);self.assertEqual(engine.call_count,1)
            team.surface['private']['snapshot_id']='another'
            with self.assertRaises(ValueError):team.execute('defense','simulate_action',{'action_id':aid})
            self.assertEqual(engine.call_count,1)

    def test_reviewer_and_defense_cannot_claim_a_different_or_unexecuted_tool(self):
        team=self.team();aid=self.action('carry');value=team.execute('defense','simulate_action',{'action_id':aid})
        answer=dict(answer='A conditional model comparison.',action_id=aid,evidence_ids=[aid+':value'],caveats=[])
        with self.assertRaises(ModelFailure):team.validate_answer({**answer,'action_id':self.action('shot')},'defense')
        team.shared['defense']={'status':'complete','result':answer}
        with self.assertRaises(ModelFailure):team.validate_answer({**answer,'verdict':'accept'},'reviewer')
        team.validate_answer({**answer,'verdict':'accept','evidence_ids':[value['evidence_id']]},'reviewer')
        checked=team.execute('reviewer','check_evidence',{})
        self.assertEqual(checked['counterfactual_tool_receipts'][0]['candidate_set_id'],self.public['candidate_set_id'])

    def test_video_revision_and_partial_assumptions_fail_closed_until_later_phases(self):
        for context in ({'video_id':'v','revision_id':'r'}, {'observation_mode':'partial_observation'},
                        {'assumption_set_id':'high'}, {'visibility_scope_id':'custom'}):
            with self.assertRaises(ValueError):
                simulate(self.request,self.public,self.private,self.snapshot,self.metadata,self.action('carry'),
                         self.public['candidate_set_id'],observation_context=context)
        for fields in ({'video_id':'v','revision_id':'r'},{'observation_mode':'partial_observation'}):
            document=copy.deepcopy(self.document);document.update(fields)
            with self.assertRaises(ValueError):Team(document,self.metadata,'Why?','fan',CONFIG,private=self.private)

    def test_six_complete_counterfactual_traces_keep_their_pre_change_digest(self):
        cases=json.loads((ROOT/'docs/reports/phase123-counterfactual-baseline.json').read_text())
        for case in cases:
            request=case['request'];snapshot,metadata,_=self.repo.resolve(request);public,private=self.repo.compare(request)
            result=simulate(request,public,private,snapshot,metadata,case['action_id'],case['candidate_set_id'])
            digest=hashlib.sha256(json.dumps(result,sort_keys=True,separators=(',',':')).encode()).hexdigest()
            self.assertEqual(digest,case['sha256'],case)


if __name__=='__main__':unittest.main()
