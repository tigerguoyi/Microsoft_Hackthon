"""The four-role team over a real decision-analysis document.

The fixture is the committed model layer, not a hand-built frame: the team is
supposed to reason over the same candidate set and evidence registry the
interface shows, so the test has to start from the same place.
"""
import copy
import json
import unittest
from unittest.mock import patch

from decision.agents import ROLES, run_team
from decision_analysis.input_adapter import NEUTRAL_PROFILE
from decision_analysis.service import Repository

CONFIG = {'model': 'test-model', 'api_key': 'secret-test-key', 'base_url': 'https://example.com/v1'}
MATCH = 'PL26-W01-MCI-CHE'


def fixture():
    """The document, metadata and a legal action the team may discuss."""
    repo = Repository()
    record = repo.index(MATCH)['records'][0]
    request = dict(match_id=MATCH, snapshot_id=record['snapshot_id'], t_ms=record['t_ms'],
                   actor_id=record['actor_id'], question='Why not pass along this route?',
                   mode='fan', language='en', profile=copy.deepcopy(NEUTRAL_PROFILE))
    document = repo.document(request)
    metadata = repo.metadata(MATCH)
    _, private = repo.compare(request)
    eligible = [c for c in document['public']['candidates'] if c.get('eligible')]
    action = next(c['action_id'] for c in eligible if c['type'] == 'pass')
    return document, metadata, private, action


def scripted_transport(action, fail=None, invalid_ref=False):
    """A provider that plays the four roles the way the contract expects."""
    requests = []

    def transport(payload):
        requests.append(copy.deepcopy(payload))
        role = next(r for r, prompt in ROLES.items() if payload['instructions'].endswith(prompt))
        if role == fail:
            raise RuntimeError('provider secret body')
        outputs = [x for x in payload['input'] if x.get('type') == 'function_call_output']
        args = {}
        if role == 'coordinator' and len(outputs) < 3:
            name = 'delegate'
            args = {'agent': ['attack', 'defense', 'reviewer'][len(outputs)]}
        elif not outputs:
            name = {'attack': 'compare_actions', 'defense': 'simulate_action',
                    'reviewer': 'check_evidence'}[role]
            if role == 'defense':
                args = {'action_id': action}
        else:
            value = {'answer': role + ' reviewed the available model evidence.',
                     'action_id': action,
                     'evidence_ids': ['invented' if invalid_ref else action + ':value'],
                     'caveats': ['Heuristic model; no real probability claim.']}
            if role == 'reviewer':
                value['verdict'] = 'accept'
                checked=json.loads(outputs[-1]['output'])
                receipts=checked.get('counterfactual_tool_receipts',[])
                if receipts and not invalid_ref:
                    value['evidence_ids'].append(receipts[0]['evidence_id'])
            return {'status': 'completed', 'output': [{'type': 'message', 'content': [
                {'type': 'output_text', 'text': json.dumps(value)}]}]}
        return {'status': 'completed', 'output': [{'type': 'function_call', 'call_id': role + str(len(outputs)),
                                                   'name': name, 'arguments': json.dumps(args)}]}

    return transport, requests


class AgentsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document, cls.metadata, cls.private, cls.action = fixture()

    def team(self, transport, question='Why pass?', mode='fan', language='en', config=CONFIG):
        return run_team(copy.deepcopy(self.document), self.metadata, question, mode, config,
                        transport, language=language, private=copy.deepcopy(self.private))

    def test_requested_language_reaches_all_agent_contexts(self):
        transport, requests = scripted_transport(self.action)
        r = self.team(transport, question='为什么传球？', language='zh')
        self.assertEqual(r['status'], 'complete')
        self.assertTrue(all('Response language: Simplified Chinese.' in p['instructions'] for p in requests))
        with self.assertRaises(ValueError):
            self.team(transport, language='invalid')

    def test_missing_config_never_calls_provider(self):
        with patch('decision.agents.urlopen') as network:
            r = self.team(scripted_transport(self.action)[0], config={})
        self.assertEqual(r['status'], 'not_configured')
        self.assertFalse(r['is_multi_agent'])
        network.assert_not_called()

    def test_four_contexts_actual_handoffs_and_tools(self):
        transport, requests = scripted_transport(self.action)
        r = run_team(copy.deepcopy(self.document), self.metadata, 'Why pass?', 'fan', CONFIG, transport,
                     private=copy.deepcopy(self.private))
        self.assertEqual(r['status'], 'complete')
        self.assertTrue(r['is_multi_agent'])
        self.assertEqual(r['model_requests'], 10)
        self.assertEqual([t['target'] for t in r['trace'] if t['event'] == 'handoff'],
                         ['attack', 'defense', 'reviewer'])
        self.assertTrue(any(t.get('tool') == 'simulate_action' for t in r['trace']))
        reviewer_request = next(p for p in requests if p['instructions'].endswith(ROLES['reviewer']))
        self.assertIn('defense', reviewer_request['input'][0]['content'])
        self.assertNotIn('secret-test-key', json.dumps(r))
        self.assertTrue(any(isinstance(e,dict) and e.get('action_id')==self.action and e.get('source_type')=='counterfactual_hypothesis' for e in r['evidence'].values()))

    def test_future_frame_fields_never_reach_the_provider(self):
        document = copy.deepcopy(self.document)
        document['snapshot']['frame']['future_events'] = ['UNSEEN_FUTURE_GOAL']
        transport, requests = scripted_transport(self.action)
        r = run_team(document, self.metadata, 'Why pass?', 'fan', CONFIG, transport,
                     private=copy.deepcopy(self.private))
        self.assertNotIn('UNSEEN_FUTURE_GOAL', json.dumps(requests))

    def test_failure_preserves_other_specialists(self):
        transport, _ = scripted_transport(self.action, fail='defense')
        r = self.team(transport)
        self.assertEqual(r['status'], 'partial')
        self.assertFalse(r['is_multi_agent'])
        self.assertEqual(r['agent_outputs']['defense']['status'], 'failed')
        self.assertEqual(r['agent_outputs']['reviewer']['status'], 'complete')
        self.assertNotIn('provider secret body', json.dumps(r))

    def test_fabricated_references_are_not_published(self):
        transport, _ = scripted_transport(self.action, invalid_ref=True)
        r = self.team(transport)
        self.assertEqual(r['status'], 'failed')
        self.assertNotIn('final', r)

    def test_early_coordinator_answer_is_rejected(self):
        answer = {'answer': 'All done', 'action_id': None,
                  'evidence_ids': ['model:limitations'], 'caveats': []}

        def transport(payload):
            return {'status': 'completed', 'output': [{'type': 'message', 'content': [
                {'type': 'output_text', 'text': json.dumps(answer)}]}]}
        r = self.team(transport)
        self.assertEqual(r['status'], 'failed')
        self.assertFalse(r['is_multi_agent'])

    def test_round_budget_stops_repeated_calls(self):
        def transport(payload):
            return {'status': 'completed', 'output': [{'type': 'function_call', 'call_id': 'x',
                                                        'name': 'unknown', 'arguments': '{}'}]}

        r = self.team(transport)
        self.assertEqual(r['status'], 'failed')
        self.assertEqual(r['model_requests'], 5)


if __name__ == '__main__':
    unittest.main()
