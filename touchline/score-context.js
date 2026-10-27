// Goal visibility follows the same available_at_ms boundary as the event list.
export function goalTimeline(events) {
  return events.filter(e => e.type === 'shot' && e.outcome === 'goal')
    .slice().sort((a,b) => a.available_at_ms-b.available_at_ms || a.sequence-b.sequence);
}
export function scoreAt(goals,time) {
  const score=[0,0];
  for (const goal of goals) {
    if (goal.available_at_ms > time) break;
    if (!['HOME','AWAY'].includes(goal.team_id)) throw Error('Goal references an unknown team');
    score[goal.team_id==='HOME'?0:1]++;
  }
  return score;
}
export const sameScore=(a,b)=>Array.isArray(a)&&Array.isArray(b)&&a.length===2&&b.length===2&&a.every((v,i)=>v===b[i]);
export function validateMatchBundle(fixture,metadata,summary,preview,events) {
  const id=fixture.match_id;
  if (metadata.match_id!==id || summary.match_id!==id || preview.match_id!==id || events.some(e=>e.match_id!==id))
    throw Error('Match identity mismatch; refusing to mix match files');
  const goals=goalTimeline(events),final=scoreAt(goals,metadata.duration_ms);
  if (!sameScore(fixture.score,summary.final_score)||!sameScore(final,summary.final_score))
    throw Error('Final score conflicts with the fixture, summary or goal events');
  for (const frame of preview.frames) {
    if (!sameScore(frame.score,scoreAt(goals,frame.t_ms))) throw Error(`Preview score disagrees with goals at ${frame.t_ms} ms`);
  }
  return goals;
}
export function scoreContext({live,clock,final,loading=false}) {
  if (loading) return 'Loading match · score unavailable';
  return live ? `Replay score at ${clock} · Final score ${final.join('–')} (FT)` : `Final score ${final.join('–')} · FT`;
}
