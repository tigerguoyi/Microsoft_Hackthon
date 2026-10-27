"""Identity migration must preserve the roster and its original attributes."""
import copy
import hashlib
import json
import unittest
from pathlib import Path

from analysis_agent import fingerprint
from generate import CLUBS, RATINGS, build_metadata, load_squads, Match, select_lineup

ROOT = Path(__file__).resolve().parents[1]


class FictionalDataTests(unittest.TestCase):
    def test_roster_attributes_are_unchanged(self):
        teams = json.loads((ROOT / 'data/league/squads.json').read_text())['teams']
        self.assertEqual(len(teams), 20)
        self.assertEqual(sum(len(t['players']) for t in teams), 566)
        self.assertEqual(len({p['name'] for t in teams for p in t['players']}), 566)
        attributes = copy.deepcopy(teams)
        for team in attributes:
            for field in ('name', 'short_name', 'stadium'):
                team.pop(field)
            for player in team['players']:
                player.pop('name')
                player.pop('sofascore', None)  # Newly collected fields; original fields must stay intact.
        digest = hashlib.sha256(json.dumps(attributes, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        # Captured before fictionalization: includes every non-name roster field,
        # order, ID, shirt number, rating, colour, nationality, birth date and age.
        self.assertEqual(digest, 'd7ee16edacf203c4f04d0d3c3cbf706fe63e4721a1a881ce9a797a0cff3de704')

    def test_generator_uses_fictional_roster(self):
        squads = load_squads()
        for club in CLUBS:
            team = squads[club['club_id']]
            for field in ('name', 'short_name', 'stadium', 'colors'):
                self.assertEqual(club[field], team[field])
            self.assertEqual(RATINGS[club['club_id']], team['rating'])
            for player in team['players']:
                self.assertRegex(player['name'], r'^[A-Z][a-z]+ Player \d{2}$')
        home, away = CLUBS[:2]
        sim = Match(123, home=home, away=away,
                    lineups=[select_lineup(c['club_id'], squads) for c in (home, away)])
        for player in build_metadata(sim)['players']:
            self.assertRegex(player['name'], r'^[A-Z][a-z]+ Player \d{2}$')

    def test_match_reports_share_roster_names(self):
        squads = load_squads()
        def check(meta):
            clubs = {t['team_id']: t['club_id'] for t in meta['teams']}
            for player in meta['players']:
                roster = squads[clubs[player['team_id']]]['players']
                expected = next(p for p in roster if p['shirt_number'] == player['jersey_number'])
                self.assertEqual(player['name'], expected['name'])
        for folder in sorted((ROOT / 'data/league/matches').iterdir()):
            meta = json.loads((folder / 'metadata.json').read_text())
            check(meta)
            report = json.loads((folder / 'analysis.json').read_text())
            summary = json.loads((folder / 'summary.json').read_text())
            events = [json.loads(line) for line in (folder / 'events.jsonl').read_text().splitlines()]
            self.assertEqual(report['source']['fingerprint'], fingerprint(meta, summary, events))
            names = {p['player_id']: p['name'] for p in meta['players']}
            for player in report['ranking']:
                self.assertEqual(player['name'], names[player['player_id']])
