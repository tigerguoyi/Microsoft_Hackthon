import {formatClock} from './core.js?v=2.2.0';
import {api,esc} from './decision-analysis-view.js?v=unified-1';
import {playerLabel,describeAction,decisionURL,validateDecisionDocument} from './player-identity.js';

// Replay keeps a brief hint. Full comparisons and all Agent calls live in Analysis.
export function createReplayDesk(getState,openDecision) {
  const $=s=>document.querySelector(s),desk=$('#replay-desk');
  const status=$('#ask-status'),analysis=$('#ask-analysis'),link=$('#replay-open-decision');
  const clock=$('#ask-clock'),follow=$('#ask-follow'),measures=$('#ask-measures'),narration=$('#ask-narration');
  let matchId='',index=null,entry=null,epoch=0,pending=null,controller=new AbortController();
  const cache=new Map();
  function collapse(buttonId,bodyId,className,label){
    const button=$(buttonId),body=$(bodyId);
    button.onclick=()=>{const open=button.getAttribute('aria-expanded')==='true';button.setAttribute('aria-expanded',String(!open));
      button.querySelector('.desk-collapse-label').textContent=open?'Show':'Hide';button.setAttribute('aria-label',`${open?'Show':'Hide'} the ${label}`);
      body.hidden=open;desk.classList.toggle(className,open);};
  }
  collapse('#collapse-data','#desk-data-body','is-data-collapsed','data board');
  collapse('#collapse-ask','#desk-ask-body','is-ask-collapsed','decision hint');
  function showBoard(mode){
    $('#player-board').hidden=mode!=='player';$('#team-board').hidden=mode==='player';
    document.querySelectorAll('[data-board]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.board===mode)));
    if(mode!=='player'){
      const team=getState().metadata?.teams.find(t=>t.team_id===(mode==='home'?'HOME':'AWAY'));
      $('#team-board-label').textContent=team?`${team.name} · totals follow the replay clock.`:'Team totals follow the replay clock.';
    }
  }
  document.querySelectorAll('[data-board]').forEach(b=>b.onclick=()=>showBoard(b.dataset.board));
  window.addEventListener('touchline-player',()=>showBoard('player'));
  function nearest(){
    const {time,playing}=getState();let row=null;
    for(const candidate of index?.records||[]){
      if(candidate.t_ms>time)break;
      if(time-candidate.t_ms<=(playing?8000:30000)&&candidate.analyzable!==false)row=candidate;
    }
    return row;
  }
  function render(row,value){
    const {metadata,time}=getState(),doc=value.doc,bundle=value.bundle;
    const best=doc.public.candidates.find(c=>c.eligible&&c.rank===1);
    entry={row,...value};link.href=decisionURL(matchId,row.decision_id);
    clock.textContent=formatClock(row.t_ms,metadata,doc.snapshot.period);
    follow.textContent=`Decision snapshot · ${((time-row.t_ms)/1000).toFixed(1)} s before playhead`;
    narration.textContent=playerLabel(bundle.metadata,bundle.request.actor_id);
    // Decision-time conditions, not the possibly later replay-frame conditions.
    const c=doc.action_conditions;
    measures.innerHTML=c?`<div><span>Decision speed</span><strong>${esc(c.speed_kmh.toFixed(1))} km/h</strong></div><div><span>Nearest opponent</span><strong>${esc(c.nearest_opponent?.distance_m?.toFixed(1)??'—')} m</strong></div>`:'';
    analysis.innerHTML=best?`<article><h4>Q2 first-ranked option</h4><p><strong>${esc(describeAction(best,bundle.metadata))}</strong></p><p>${esc(best.opportunity)}</p><p class="ask-risk">${esc(best.main_risk)}</p></article>`:'<p>No supported Q2 comparison at this snapshot.</p>';
    status.textContent='Open Decision Analysis to compare every choice, explore a counterfactual or ask the AI coach.';
  }
  function clearHint(message){entry=null;analysis.replaceChildren();measures.replaceChildren();narration.textContent='';clock.textContent='—';status.textContent=message;
    link.href=matchId?decisionURL(matchId):'index.html?view=stats&analysis=decisions';}
  function clear(){epoch++;controller.abort();controller=new AbortController();matchId='';index=null;pending=null;cache.clear();clearHint('Select a match.');follow.textContent='Waiting for a match';}
  link.onclick=event=>{event.preventDefault();if(matchId)openDecision?.(entry?.row.decision_id);};
  async function read(row){
    if(pending)return;
    const revision=epoch,sourceMatch=matchId,key=`${sourceMatch}:${row.decision_id}`;pending=key;
    status.textContent='Reading this registered decision…';
    try{
      const bundle=await api(`context?match_id=${encodeURIComponent(sourceMatch)}&decision_id=${encodeURIComponent(row.decision_id)}`,undefined,controller.signal);
      const doc=await api('analyze',bundle.request,controller.signal);
      if(revision!==epoch||sourceMatch!==matchId)return;
      validateDecisionDocument(doc,bundle);const value={bundle,doc};cache.set(key,value);
      if(cache.size>12)cache.delete(cache.keys().next().value);
      if(nearest()?.decision_id===row.decision_id)render(row,value);
    }catch(error){if(revision===epoch&&error.name!=='AbortError')clearHint(error.message);}
    finally{if(revision===epoch)pending=null;}
  }
  return {clear,showTeam(teamId){showBoard(teamId==='AWAY'?'away':'home');},setMatch(id){
    clear();matchId=id;const revision=epoch;link.href=decisionURL(id);
    status.textContent='Loading decision index…';
    api(`index?match_id=${encodeURIComponent(id)}`,undefined,controller.signal).then(value=>{
      if(revision!==epoch||value.match_id!==matchId)return;index=value;
      follow.textContent=`${value.records.length.toLocaleString()} registered decisions`;
      status.textContent='Pause near a possession for a brief Q2 hint.';
    }).catch(error=>{if(revision===epoch&&error.name!=='AbortError')status.textContent=error.message;});
  },sync(){
    const state=getState();if(state.loading||!index||state.metadata?.match_id!==matchId)return;
    const row=nearest();
    if(!row){clearHint('No registered decision in this time window. Open Decision Analysis to browse the full match.');return;}
    if(entry?.row.decision_id===row.decision_id){render(row,entry);return;}
    const value=cache.get(`${matchId}:${row.decision_id}`);
    if(value)render(row,value);
    else if(!state.playing)read(row);
    else clearHint('Pause to read this decision. Full candidate comparison and AI questions are in Decision Analysis.');
  }};
}
