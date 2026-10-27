"""Read-only, full-league identity/score audit. Never regenerates match data.

Run from touchline: python scripts/audit_decision_consistency.py --output docs/reports/decision-consistency.json
Full tracking is streamed when present; absent tracking is explicitly reported.
"""
import argparse
import bisect
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path


def jsonl(path):
    opener = gzip.open if str(path).endswith('.gz') else open
    with opener(path, 'rt', encoding='utf-8') as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


def score_at(goals, t_ms):
    i = bisect.bisect_right([g['available_at_ms'] for g in goals], t_ms)
    return [sum(g['team_id'] == team for g in goals[:i]) for team in ('HOME', 'AWAY')]


def identity_errors(actor_id, candidates, frame, metadata):
    """Validate internal IDs against this match and active frame, never shirt digits."""
    roster = {p['player_id']: p for p in metadata['players']}
    active = {p[0] for p in frame['players']}
    errors = []
    if len(roster) != len(metadata['players']) or len(active) != len(frame['players']):
        errors.append('duplicate_player_id')
    if actor_id not in roster or actor_id not in active:
        return errors + ['inactive_or_unknown_actor']
    for c in candidates:
        if c.get('type', c.get('kind')) != 'pass':
            continue
        key = c.get('action_id', c.get('key', ''))
        receiver = key.split(':', 1)[1] if key.startswith('pass:') else None
        p = roster.get(receiver)
        reasons = []
        if p is None:
            reasons.append('unknown_receiver')
        elif p['team_id'] != roster[actor_id]['team_id']:
            reasons.append('opponent_receiver')
        if receiver == actor_id:
            reasons.append('self_pass')
        if receiver not in active:
            reasons.append('inactive_receiver')
        explicit = c.get('recipient_id', c.get('recipient'))
        if explicit is not None and explicit != receiver:
            reasons.append('recipient_action_mismatch')
        errors.extend(key + ':' + reason for reason in reasons)
    return errors


def source_hashes(root):
    files = []
    for folder in ('data/league', 'data/decision-analysis', 'decision_analysis', 'decision', '../deploy', '../.github/workflows'):
        files.extend(p for p in (root / folder).rglob('*') if p.is_file()
                     and '__pycache__' not in p.parts and p.suffix not in ('.pyc',))
    files += [root / p for p in ('generate.py', 'server.py', 'model_service.py', 'startup.sh', 'wsgi.py')]
    result = {}
    for path in sorted(set(files)):
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(block)
        result[str(path.relative_to(root))] = digest.hexdigest()
    return result


def audit(root):
    league = json.loads((root / 'data/league/league.json').read_text())
    fixtures = {m['match_id']: m for w in league['weeks'] for m in w['matches']}
    fixture_lines = {m['match_id']: m for m in jsonl(root / 'data/league/fixtures.jsonl')}
    manifest = json.loads((root / 'data/decision-analysis/manifest.json').read_text())
    result = dict(schema_version='decision-consistency-1', matches=[], totals=Counter(), errors=[],
                  limitations=['Full tracking is checked only if present; missing files are not fabricated.',
                               'All cached candidate identities are checked; full Q2 recomputation uses a separate regression sample.',
                               'This audit tests consistency, not real-football tactical validity.'])
    # Source Q2 candidate construction only: no value recursion, no re-simulation.
    import sys
    sys.path.insert(0, str(root))
    from decision_analysis.q2 import _scope
    for entry in manifest['matches']:
        match = entry['match_id']; folder = root / 'data/league/matches' / match
        metadata = json.loads((folder / 'metadata.json').read_text())
        summary = json.loads((folder / 'summary.json').read_text())
        events = list(jsonl(folder / 'events.jsonl'))
        goals = sorted((e for e in events if e['type'] == 'shot' and e.get('outcome') == 'goal'),
                       key=lambda e: (e['available_at_ms'], e['sequence']))
        final = score_at(goals, metadata['duration_ms'])
        errors = []; counts = Counter(); roster = {p['player_id']: p for p in metadata['players']}
        for name, actual in [('league.fixture', fixtures[match]['score']), ('fixtures.jsonl', fixture_lines[match]['score']),
                             ('summary', summary['final_score'])]:
            if actual != final:
                errors.append(dict(kind='final_score', source=name, actual=actual, expected=final))
        for goal in goals:
            if goal['score'] != score_at(goals, goal['available_at_ms']):
                errors.append(dict(kind='goal_event_score', event_id=goal['event_id']))
        def check_frame(frame, source):
            counts[source + '_frames'] += 1
            expected = score_at(goals, frame['t_ms'])
            if frame['score'] != expected:
                errors.append(dict(kind='frame_score', source=source, t_ms=frame['t_ms'], actual=frame['score'], expected=expected))
        preview = json.loads((folder / 'preview-60s.json').read_text())
        for frame in preview['frames']:
            check_frame(frame, 'preview')
        for state in jsonl(folder / 'states.jsonl'):
            if 'score' in state:
                check_frame(state, 'statistics')
        source_frames={}
        for decision in jsonl(folder / 'decisions.jsonl'):
            check_frame(decision['snapshot'], 'source_decision')
            source_frames[decision['decision_id']]=decision['snapshot']
        tracking = folder / 'tracking.jsonl'
        if not tracking.exists() and (folder / 'tracking.jsonl.gz').exists():
            tracking = folder / 'tracking.jsonl.gz'
        if tracking.exists():
            for frame in jsonl(tracking):
                check_frame(frame, 'full_tracking')
        cache = root / 'data/decision-analysis/matches' / match
        scored = {r['snapshot_id']: r for r in json.loads(gzip.open(cache / 'scored.json.gz', 'rt').read())}
        active_signatures = set()
        for record in jsonl(cache / 'snapshots.jsonl.gz'):
            snap = record['snapshot']; frame = snap['frame']; actor = frame['ball_owner_id']
            counts['snapshots'] += 1; check_frame(frame, 'analysis_snapshot')
            if snap['match_id'] != match or snap['t_ms'] != frame['t_ms']:
                errors.append(dict(kind='snapshot_binding', decision_id=record['decision_id']))
            public = scored.get(snap['snapshot_id'], {}).get('response')
            if public is None:
                errors.append(dict(kind='missing_cached_response', decision_id=record['decision_id']));continue
            if public['snapshot_id'] != snap['snapshot_id'] or public['data_version'] != snap['data_version']:
                errors.append(dict(kind='cache_binding', decision_id=record['decision_id']))
            if source_frames.get(record['decision_id']) != frame:
                errors.append(dict(kind='source_snapshot_mismatch', decision_id=record['decision_id']))
            candidates = public['candidates']
            if not frame['in_play'] and not candidates:
                counts['unsupported_terminal_snapshots']+=1
                continue
            counts['analyzable_snapshots']+=1
            state=dict(actor=actor,team=int(roster[actor]['team_id']=='AWAY'),period=frame['period'],ball=frame['ball'],
                attacking_direction=snap['attacking_direction'],players=[dict(id=p[0],team=int(roster[p[0]]['team_id']=='AWAY'),
                x=p[1],y=p[2],vx=p[3],vy=p[4],position=roster[p[0]]['position']) for p in frame['players']])
            scoped,functions,reverse=_scope(state)
            generated={reverse.get(c['recipient'],c['recipient']):c for c in functions['candidate_actions'](scoped) if c['kind']=='pass'}
            if set(generated)!={c['action_id'].split(':',1)[1] for c in candidates if c['type']=='pass'}:
                errors.append(dict(kind='candidate_set_identity', decision_id=record['decision_id']))
            for receiver,candidate in generated.items():
                player=next(p for p in frame['players'] if p[0]==receiver)
                expected=[player[1]+.25*player[3],player[2]+.25*player[4]]
                counts['predicted_receiving_points']+=1
                if any(abs(a-b)>1e-9 for a,b in zip(expected,candidate['target'])):
                    errors.append(dict(kind='predicted_target',decision_id=record['decision_id'],receiver=receiver))
            issues = identity_errors(actor, candidates, frame, metadata)
            errors.extend(dict(kind='identity', decision_id=record['decision_id'], detail=e) for e in issues)
            active = {p[0] for p in frame['players']};active_signatures.add(tuple(sorted(active)))
            for c in candidates:
                if c['type'] != 'pass':continue
                counts['pass_candidates'] += 1;counts[roster[actor]['team_id'] + '_pass_candidates'] += 1
                receiver = roster.get(c['action_id'].split(':', 1)[1])
                if receiver:
                    counts['keeper_receivers' if receiver['position'] == 'GK' else 'outfield_receivers'] += 1
                    if not receiver['starter']:counts['substitute_receivers'] += 1
            counts['period_' + str(snap['period'])] += 1
        result['totals'].update(counts)
        row = dict(match_id=match, final_score=final, goals=[{k:g[k] for k in ('event_id','available_at_ms','team_id','score')} for g in goals],
                   counts=dict(counts), active_lineups=len(active_signatures), full_tracking_available=tracking.exists(), errors=errors)
        if match == 'PL26-W03-EVE-CRY':
            row['regression'] = dict(players=[{k:roster[p][k] for k in ('player_id','team_id','jersey_number','name','position')}
                                              for p in ('H10','A08')],
                                     score_at_69_30=score_at(goals, next(p['start_ms'] for p in metadata['periods'] if p['period']==2) + (69*60+30-45*60)*1000),
                                     explanation='The first half includes five added minutes; 69:30 maps through metadata period start, not wall-clock milliseconds.',
                                     preview_score_differs_from_final=any(f['score'] != final for f in preview['frames']))
        result['matches'].append(row)
        result['errors'].extend(dict(match_id=match, **e) for e in errors)
    result['totals'] = dict(result['totals'])
    result['match_count'] = len(result['matches'])
    result['full_tracking_matches'] = sum(m['full_tracking_available'] for m in result['matches'])
    result['source_commit'] = manifest['source_commit']
    result['status'] = 'pass' if not result['errors'] else 'fail'
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--hash-output', type=Path)
    args = parser.parse_args()
    protected=(args.root.resolve()/'data').resolve()
    for output in (args.output,args.hash_output):
        if output and output.resolve().is_relative_to(protected):
            parser.error('Read-only audit refuses to write inside the source data directory')
    result = audit(args.root.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    if args.hash_output:
        args.hash_output.write_text(json.dumps(source_hashes(args.root.resolve()), indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('matches','limitations','errors')}, ensure_ascii=False))
    print('Errors:', len(result['errors']))
    raise SystemExit(bool(result['errors']))


if __name__ == '__main__':
    main()
