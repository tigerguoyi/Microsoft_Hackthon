// IDs are match-local keys. Never turn H10/A08 into a shirt number or club code.
export function resolvePlayer(metadata, playerId) {
  const matches = (metadata?.players || []).filter(p => p.player_id === playerId);
  const player = matches.length === 1 ? matches[0] : null;
  const teams = (metadata?.teams || []).filter(t => t.team_id === player?.team_id);
  const team = teams.length === 1 ? teams[0] : null;
  const valid = !!player && !!team && player.jersey_number != null && !!player.name;
  const abbreviation = team?.abbreviation || team?.club_id || team?.short_name || team?.name;
  return {valid, player_id: playerId, team_id: player?.team_id, club_id: team?.club_id,
    short_name: team?.short_name, jersey_number: player?.jersey_number, name: player?.name,
    position: player?.position, player, team,
    label: valid ? `${abbreviation} #${player.jersey_number} · ${player.name}`
      : `Unverified player ${player?.name || playerId || 'unknown'} (${playerId || 'unknown ID'})`};
}

export const playerLabel = (metadata, playerId) => resolvePlayer(metadata, playerId).label;

export function candidateIdentityIssues(candidate, snapshot, metadata, actorId) {
  if (candidate.type !== 'pass') return [];
  const issues = [], receiverId = candidate.action_id?.startsWith('pass:') ? candidate.action_id.slice(5) : null;
  const receiver = resolvePlayer(metadata, receiverId), actor = resolvePlayer(metadata, actorId);
  const frame = snapshot?.frame || snapshot;
  const onPitch = frame?.players?.find(p => p[0] === receiverId);
  if (!receiver.valid) issues.push('Receiver identity cannot be resolved in this match');
  if (!actor.valid || receiver.team_id !== actor.team_id) issues.push('Receiver must belong to the acting team');
  if (receiverId === actorId) issues.push('A player cannot pass to themselves');
  if (!onPitch) issues.push('Receiver is not active in this snapshot');
  if (candidate.recipient_id != null && candidate.recipient_id !== receiverId) issues.push('Candidate recipient and action ID disagree');
  if (candidate.target && onPitch) {
    const expected = [onPitch[1] + .25 * onPitch[3], onPitch[2] + .25 * onPitch[4]];
    if (candidate.target.length !== 2 || candidate.target.some((v,i) => !Number.isFinite(v) || Math.abs(v-expected[i]) > 1e-6))
      issues.push('Target does not match this receiver and the Q2 quarter-second lead');
  }
  return issues;
}

export function validateDecisionDocument(doc, bundle) {
  if (doc.match_id !== bundle.snapshot.match_id || doc.snapshot_id !== bundle.snapshot.snapshot_id ||
      doc.data_version !== bundle.snapshot.data_version || doc.snapshot?.snapshot_id !== bundle.snapshot.snapshot_id)
    throw Error('Stale or mismatched decision source; reload this match.');
  const byId = new Map((doc.candidates || []).map(c => [c.action_id,c]));
  for (const candidate of doc.public.candidates) {
    const rich = byId.get(candidate.action_id);
    if (candidate.type !== 'hold' && (!rich || rich.rank !== candidate.rank || rich.eligible !== candidate.eligible))
      throw Error('Public and diagnostic candidates disagree; analysis is not displayed.');
    const issues = candidateIdentityIssues({...candidate,...rich}, bundle.snapshot, bundle.metadata, bundle.request.actor_id);
    if (issues.length) throw Error(`Data inconsistency for ${candidate.action_id}: ${issues.join('; ')}`);
  }
}

export function describeAction(candidate, metadata) {
  if (!candidate) return 'Unavailable action';
  if (candidate.type === 'pass') return `Pass to ${playerLabel(metadata, candidate.action_id?.slice(5))}`;
  if (candidate.type === 'carry') return `Carry ${candidate.action_id?.split(':')[1] || ''}`;
  return candidate.type === 'shot' ? 'Shoot' : 'Hold';
}

export function decisionURL(matchId, decisionId, actionId) {
  const query = new URLSearchParams({view:'decisions',match:matchId});
  if (decisionId) query.set('decision',decisionId);
  if (actionId) query.set('action',actionId);
  return `index.html?${query}`;
}
