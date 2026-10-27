"""Human-revised partial annotations. Unknown identities/velocity remain unknown.

Reuses Jolin's calibrated landmarks and immutable revision pattern, not its 22-player gate.
"""
import copy
import math
import re
from .geometry import calibrate, project, point, number
from .storage import asset, folder, write, digest, LOCK

VERSION = 'partial-snapshot-1'
LIMITATIONS = ['Human-confirmed annotations are not independently verified ground truth.',
    'Ground-plane calibration cannot locate elevated balls.',
    'Unseen, undetected and user-excluded players are not confirmed absent.',
    'Unknown velocity uses an explicit neutral-zero prediction assumption, not an observed stationary player.',
    'Scenario rankings are unvalidated conditional utilities, not success probabilities or full-field optimal decisions.']


def integer(x, lo, hi):
    if type(x) is not int or not lo <= x <= hi:
        raise ValueError('Invalid integer')
    return x


def confirm(video_id, draft, owner, root=None):
    a = asset(video_id, owner, root)
    if not isinstance(draft, dict) or set(draft) != {'video_id', 'parent_revision_id', 'rights_confirmed', 'frames'} or draft['video_id'] != video_id or draft['rights_confirmed'] is not True:
        raise ValueError('Expected authorized versioned annotation')
    frames = draft['frames']
    if not isinstance(frames, list) or not 1 <= len(frames) <= 60:
        raise ValueError('Annotate 1–60 moments')
    clean = []; timestamps = set()
    for f in frames:
        if set(f) != {'timestamp_ms', 'actor_id', 'possession_team', 'attack_direction', 'ball_image', 'players', 'landmarks', 'confirmed', 'unknown_opponent_count', 'coverage_complete'}:
            raise ValueError('Invalid annotation frame fields')
        t = integer(f['timestamp_ms'], 0, a['duration_ms'] - 1)
        if t in timestamps:
            raise ValueError('Duplicate timestamp')
        timestamps.add(t)
        if f['possession_team'] not in ('HOME', 'AWAY', None) or f['attack_direction'] not in ('positive_x', 'negative_x', None):
            raise ValueError('Invalid team or direction')
        if type(f['coverage_complete']) is not bool:
            raise ValueError('Explicit coverage confirmation required')
        if set(f['confirmed']) != {'calibration', 'direction', 'possession', 'ground_ball'} or any(type(v) is not bool for v in f['confirmed'].values()):
            raise ValueError('Explicit boolean human confirmations required')
        if f['unknown_opponent_count'] is not None:
            integer(f['unknown_opponent_count'], 0, 11)
        if f['ball_image'] is not None:
            point(f['ball_image'])
        if not isinstance(f['players'], list) or len(f['players']) > 22:
            raise ValueError('At most 22 observed players')
        seen = set()
        for p in f['players']:
            required = {'player_id', 'track_id', 'team_id', 'image', 'position', 'name', 'jersey_number', 'velocity', 'confidence', 'human_verified', 'identity_status', 'observation_status'}
            if set(p) != required or not isinstance(p['player_id'], str) or not re.fullmatch('T[0-9]{2,6}', p['player_id']) or p['player_id'] in seen:
                raise ValueError('Invalid/duplicate stable temporary identity')
            seen.add(p['player_id']); point(p['image']); number(p['confidence'], 0, 1)
            if p['team_id'] not in ('HOME', 'AWAY', None) or p['position'] not in ('GK', 'OUTFIELD', None) or p['identity_status'] not in ('temporary', 'confirmed') or p['observation_status'] not in ('visible', 'occluded', 'undetected', 'outside_view') or type(p['human_verified']) is not bool:
                raise ValueError('Invalid observation attributes')
            if p['track_id'] is not None:
                integer(p['track_id'], 0, 10000000)
            if p['jersey_number'] is not None:
                integer(p['jersey_number'], 1, 99)
            if p['name'] is not None and (not isinstance(p['name'], str) or len(p['name']) > 64):
                raise ValueError('Invalid optional display name')
            if p['velocity'] is not None:
                if not isinstance(p['velocity'], list) or len(p['velocity']) != 2 or math.hypot(*(number(v, -12, 12) for v in p['velocity'])) > 12:
                    raise ValueError('Invalid reviewed velocity')
        if f['actor_id'] is not None and f['actor_id'] not in seen:
            raise ValueError('Carrier identity must be in this frame')
        calibration = None; errors = []
        try:
            calibration = calibrate(f['landmarks'])
        except ValueError as e:
            errors.append(str(e))
        observations = []
        for p in f['players']:
            p = copy.deepcopy(p); p['pitch'] = None; p['position_confidence'] = None; p['is_ball_carrier'] = p['player_id'] == f['actor_id']
            if calibration:
                try:
                    p['pitch'] = project(calibration['matrix'], p['image'])
                except ValueError:
                    errors.append('Invalid pitch position: ' + p['player_id'])
            observations.append(p)
        ball = None
        if calibration and f['ball_image'] is not None:
            try:
                ball = project(calibration['matrix'], f['ball_image'])
            except ValueError:
                errors.append('Invalid ball projection')
        clean.append(dict(**copy.deepcopy(f), observed_players=observations, ball_position=ball, calibration=calibration, calibration_errors=errors))
    clean.sort(key=lambda x: x['timestamp_ms'])
    # IDs are user-correctable mappings; every merge/split generates a new revision.
    canonical=copy.deepcopy(draft)
    canonical['frames'].sort(key=lambda f:f['timestamp_ms'])
    rid = digest([VERSION, a['sha256'], canonical])
    record = dict(schema_version=VERSION, video_id=video_id, revision_id=rid, parent_revision_id=draft['parent_revision_id'],
                  source='real_video', annotation=canonical, frames=clean, limitations=LIMITATIONS)
    with LOCK:
        current = asset(video_id, owner, root)
        if current['latest_revision_id'] != draft['parent_revision_id']:
            raise ValueError('Stale parent revision; do not overwrite another edit')
        write(folder(video_id, root) / ('revision-' + rid + '.json'), record)
        current['latest_revision_id'] = rid; write(folder(video_id, root) / 'asset.json', current)
    return record


def snapshot(record, index, scope='verified', selected=None):
    f = record['frames'][integer(index, 0, len(record['frames']) - 1)]
    if scope not in ('verified', 'confirmed_only', 'custom'):
        raise ValueError('Unknown visibility scope')
    observed = f['observed_players']
    if scope == 'custom':
        if not isinstance(selected, list) or len(set(selected)) != len(selected) or set(selected) - {p['player_id'] for p in observed}:
            raise ValueError('Invalid custom visibility selection')
    else:
        selected = [p['player_id'] for p in observed]
    players = [copy.deepcopy(p) for p in observed if p['player_id'] in selected and p['human_verified'] and p['pitch'] is not None and p['team_id'] is not None and p['observation_status'] == 'visible' and p['confidence'] >= .5 and (scope != 'confirmed_only' or p['identity_status'] == 'confirmed')]
    scope_id = 'scope-' + digest([scope, sorted(selected), [p['player_id'] for p in players]])
    actor = next((p for p in players if p['player_id'] == f['actor_id']), None)
    reasons = list(f['calibration_errors'])
    reasons += ['Human confirmation required: ' + k for k, v in f['confirmed'].items() if not v]
    if f['attack_direction'] is None:
        reasons.append('Attack direction unknown')
    if not actor or actor['team_id'] != f['possession_team']:
        reasons.append('Confirmed attacking carrier unavailable in selected scope')
    if f['ball_position'] is None:
        reasons.append('Ball position unknown')
    elif actor and math.dist(f['ball_position'], actor['pitch']) > 2:
        reasons.append('Ball/carrier control relationship exceeds 2 m')
    team = f['possession_team']
    teammates = [p for p in players if p['team_id'] == team and p['player_id'] != f['actor_id']]
    opponents = [p for p in players if p['team_id'] != team]
    if any(sum(p['team_id'] == t for p in players) > 11 for t in ('HOME', 'AWAY')):
        reasons.append('More than 11 selected players on a team')
    unknown = f['unknown_opponent_count']
    excluded_opponents = sum(p['team_id'] != team and p['team_id'] is not None and p not in players for p in observed)
    if unknown is not None:
        unknown += excluded_opponents  # Excluded observed defenders become unknown to this evaluation.
        if unknown + len(opponents) > 11:
            reasons.append('Opponent count exceeds 11')
    all_complete = f['coverage_complete'] and len(players) == 22 and all(sum(p['team_id'] == t for p in players) == 11 and sum(p['team_id'] == t and p['position'] == 'GK' for p in players) == 1 for t in ('HOME', 'AWAY'))
    if all_complete:unknown=0
    if f['coverage_complete'] and not all_complete:
        reasons.append('Full observation claim does not match selected players and keepers')
    value = dict(schema_version=VERSION, source='real_video', video_id=record['video_id'], revision_id=record['revision_id'], frame_index=index,
        timestamp_ms=f['timestamp_ms'], possession_team=team, ball_carrier_id=f['actor_id'], attack_direction=f['attack_direction'], ball_position=f['ball_position'],
        observed_players=players, observed_teammates=teammates, observed_opponents=opponents, visibility_scope_id=scope_id,
        observation_mode='full_observation' if all_complete else 'partial_observation',
        unknown_state=dict(unknown_defender_count=unknown if unknown is not None else 'unknown', goalkeeper='observed' if any(p['position'] == 'GK' for p in opponents) else 'unknown', offside_line='known' if all_complete else 'unknown', excluded_ids=[p['player_id'] for p in observed if p not in players],excluded_observations=[dict(player_id=p['player_id'],observation_status=p['observation_status'],user_excluded=p['player_id'] not in selected,human_verified=p['human_verified']) for p in observed if p not in players]),
        observation_quality=dict(ready=not reasons, blocking_reasons=reasons, calibration_status='human_reviewed' if f['confirmed']['calibration'] and f['calibration'] else 'unverified', human_verification='reviewed'), limitations=LIMITATIONS)
    value['snapshot_id'] = 'video-' + digest(value)
    return value
