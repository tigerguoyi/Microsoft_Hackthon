"""Full-league consistency and immutable numerical/deployment and versioned adapter regression."""
import hashlib
import json
from pathlib import Path
import unittest

from decision_analysis.service import Repository
from scripts.audit_decision_consistency import audit, identity_errors

ROOT=Path(__file__).resolve().parents[1]


class DecisionUnificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report=audit(ROOT)

    def test_every_cached_pass_and_pre_action_snapshot_passes_identity_and_score_audit(self):
        self.assertEqual(self.report['status'],'pass',self.report['errors'])
        self.assertEqual(self.report['match_count'],40)
        self.assertEqual(self.report['totals']['snapshots'],91031)
        self.assertEqual(self.report['totals']['pass_candidates'],904995)
        self.assertEqual(self.report['totals']['predicted_receiving_points'],904995)
        self.assertEqual(self.report['totals']['unsupported_terminal_snapshots'],2)
        for key in ('HOME_pass_candidates','AWAY_pass_candidates','period_1','period_2','substitute_receivers','keeper_receivers'):
            self.assertGreater(self.report['totals'][key],0)

    def test_ivory_score_difference_is_a_time_difference_not_a_changed_result(self):
        match=next(m for m in self.report['matches'] if m['match_id']=='PL26-W03-EVE-CRY')
        self.assertEqual(match['final_score'],[1,1]);self.assertEqual(match['regression']['score_at_69_30'],[0,1])
        self.assertEqual(match['regression']['players'][0]['jersey_number'],11)
        self.assertEqual(match['regression']['players'][1]['jersey_number'],10)

    def test_source_data_q2_and_azure_unchanged_with_explicit_versioned_adapter_changes(self):
        hashes=json.loads((ROOT/'docs/reports/protected-source-hashes.json').read_text())
        approved=json.loads((ROOT/'docs/reports/phase123-approved-source-changes.json').read_text())
        extended=json.loads((ROOT/'docs/reports/video-approved-source-changes.json').read_text())['changes']
        self.assertEqual(set(extended),{'decision/agents.py','decision_analysis/counterfactual.py','server.py','wsgi.py'})
        for relative,entry in extended.items():
            self.assertEqual(entry['before'],approved['changes'].get(relative,{}).get('after',hashes.get(relative)))
            self.assertEqual(hashlib.sha256((ROOT/relative).read_bytes()).hexdigest(),entry['after'],relative)
        expected_adapters={'decision/agents.py','decision_analysis/counterfactual.py','server.py'}
        self.assertEqual(set(approved['changes']),expected_adapters|{'decision_analysis/counterfactual_summary.py'})
        for relative,entry in approved['changes'].items():
            self.assertEqual(entry['before'],hashes.get(relative),relative)
            self.assertEqual(hashlib.sha256((ROOT/relative).read_bytes()).hexdigest(),extended.get(relative,entry)['after'],relative)
        for relative,expected in hashes.items():
            content=(ROOT/relative).read_bytes()
            if relative=='../.github/workflows/ci.yml':
                self.assertEqual(content.count(b'      - name: Install Touchline test dependencies\n'),1)
                content=content.replace(b'      - name: Install Touchline test dependencies\n        working-directory: touchline\n        run: npm ci --ignore-scripts\n',b'')
            expected=approved['changes'][relative]['after'] if relative in expected_adapters else expected
            expected=extended.get(relative,{}).get('after',expected)
            self.assertEqual(hashlib.sha256(content).hexdigest(),expected,relative)

    def test_six_preexisting_q2_responses_and_numeric_branches_are_unchanged(self):
        repo=Repository()
        for case in json.loads((ROOT/'docs/reports/q2-regression-baseline.json').read_text()):
            public,private=repo.compare(case['request']);self.assertEqual(public,case['public'])
            self.assertEqual([{k:r.get(k) for k in ('key','q','probabilities')} for r in private.get('options',[])],case['q'])

    def test_identity_auditor_rejects_missing_cross_team_self_and_inactive_receivers(self):
        metadata={'players':[{'player_id':'H10','team_id':'HOME'},{'player_id':'H08','team_id':'HOME'},{'player_id':'A08','team_id':'AWAY'}]}
        frame={'players':[['H10'],['A08']]}
        for receiver in ('A08','H10','H08','H99'):
            self.assertTrue(identity_errors('H10',[{'type':'pass','action_id':'pass:'+receiver}],frame,metadata))


if __name__=='__main__':unittest.main()
