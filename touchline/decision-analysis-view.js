import {playerLabel,describeAction,validateDecisionDocument} from './player-identity.js';
import {createDecisionAgent} from './decision-agent.js';
import {renderPitch} from './pitch-renderer.js?v=phase123-1';
export const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c]);
const fmt=(v,n=2)=>v==null?'—':Number(v).toFixed(n);
export const actionLabel=describeAction;
export function filterDecisionRecords(rows,f,rep=[],largest=[]){
 const ids=new Set(f.scope==='largest'?largest:rep);
 return rows.filter(r=>(!f.team||r.team_id===f.team)&&(!f.player||r.actor_id===f.player)&&(!f.kind||r.kind===f.kind)&&
   (f.scope==='all'||f.scope==='coverage'&&!r.analyzable||['representative','largest'].includes(f.scope)&&ids.has(r.decision_id)));
}
export function conditionsMarkup(c,metadata){
 if(!c)return '<p class="empty">Current ball-owner tracking is unavailable.</p>';
 const nearest=c.nearest_opponent,name=id=>playerLabel(metadata,id);
 const facts=[['Movement speed',`${fmt(c.speed_mps)} m/s`,`${fmt(c.speed_kmh,1)} km/h`],
  ['Movement direction',c.movement_heading_deg==null?'Stationary / slow':`${fmt(c.movement_heading_deg,1)}°`,c.movement_label],
  ['Nearest defender',`${fmt(nearest?.distance_m)} m`,nearest?name(nearest.player_id):'Unavailable'],
  ['3 m proximity',c.under_pressure_3m?'Under pressure':'Space available','Distance indicator, not a measured tackle threat'],
  ['Opponents within 5 m',c.opponents_within_5m,'Including the opposing goalkeeper'],['Distance to ball',`${fmt(c.ball_distance_m)} m`,'Observed player and ball positions']];
 return `<section class="action-conditions"><span class="tiny-label">DECISION-TIME TRACKING</span><h3>Player action conditions</h3><dl class="action-conditions-grid">${facts.map(([k,v,n])=>`<div><dt>${esc(k)}</dt><dd>${esc(v)}</dd><small>${esc(n)}</small></div>`).join('')}</dl><p class="decision-note">Velocity is not body orientation. Pitch angles: 0° right, 90° down; movement labels follow the explicit attacking direction. Unknown or slow movement has no heading.</p></section>`;
}
export async function api(path,data,signal){
 const r=await fetch('/api/decision-analysis/'+path,{signal,cache:'no-store',...(data===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)})});
 const value=await r.json();if(!r.ok)throw Error(value.error||`Analysis unavailable (${r.status})`);return value;
}
export function createDecisionView(container,jump){
 container.innerHTML=`<nav class="decision-return-links" aria-label="Other match views"><button class="button" data-view="replay">Replay</button><button class="button" data-view="stats">Match Report</button><button class="button" data-view="home">Home</button></nav><div class="decision-header"><div><span class="tiny-label">CURRENT GENERATOR · TWO-STEP ANALYSIS</span><h2>Compare the choices, keep the facts.</h2><p>Current-match snapshots, opportunities and risks. Hypotheses stay separate from actual results.</p></div><span class="subtle-badge">SOURCE: DATA/LEAGUE</span></div>
 <div class="decision-toolbar"><label>Team<select id="da-team"><option value="">Both teams</option></select></label><label>Decision player<select id="da-player"><option value="">All players</option></select></label><label>Actual action type<select id="da-kind"><option value="">All actions</option><option value="pass">Pass</option><option value="carry">Carry</option><option value="shot">Shot</option></select></label><label>Scope<select id="da-scope"><option value="representative">Representative decisions</option><option value="all">All decisions</option><option value="largest">Largest value losses</option><option value="coverage">Unavailable / coverage</option></select></label></div>
 <p id="da-status" role="status"></p><div id="da-summary" class="decision-summary"></div><p class="decision-note">Representatives rotate players, teams, zones and possession episodes. Missing eligible records are never invented. Largest losses is a separate review list, not a representative sample.</p>
 <div class="decision-workspace"><aside class="card decision-list-card"><div class="card-heading"><h3>Decision timeline</h3><span id="da-count"></span></div><div id="da-list"></div><p class="decision-note" id="da-window"></p><button class="button" id="da-earlier" hidden>Earlier decisions</button><button class="button" id="da-more" hidden>Show more decisions</button></aside><div id="da-detail"><p class="empty">Select a decision.</p></div></div>`;
 const $=s=>container.querySelector(s);let context=null,index=null,doc=null,bundle=null,current=null,selected=null,actual=null,shown=false,page=30,listStart=0,epoch=0,requestId=0,loading=false,abort=new AbortController(),decisionAbort=new AbortController(),pendingDecision=null;
 const agent=createDecisionAgent(api,()=>renderAgent());
 const filters=()=>Object.fromEntries(['team','player','kind','scope'].map(k=>[k,$('#da-'+k).value]));
 const label=id=>playerLabel(context.metadata,id);
 function save(){try{sessionStorage.setItem('decision-filters:'+context.metadata.match_id,JSON.stringify(filters()));}catch{}}
 function paint(){if(!doc||!bundle)return;const c=$('#da-pitch'),a=doc.candidates.find(c=>c.action_id===selected),actualOption=actual&&doc.candidates.find(c=>c.action_id===actual.actual_action_id);
  renderPitch(c,doc.snapshot.frame,{metadata:bundle.metadata,selected:bundle.request.actor_id,route:a?.eligible?{start:doc.snapshot.frame.ball,target:a.target,recipient_id:a.type==='pass'?a.recipient_id:null}:null,actualRoute:actualOption?{start:doc.snapshot.frame.ball,target:actualOption.target}:null});}
 function renderDetail(){
  if(!doc||!bundle)return;
  const options=doc.candidates,choice=options.find(a=>a.action_id===selected),clock=context.clock(doc.snapshot.t_ms,doc.snapshot.period);
  const canJump=context.fullReady()||doc.snapshot.t_ms>=context.preview.start_ms&&doc.snapshot.t_ms<=context.preview.end_ms;
  const path=new URL('decision-counterfactual.html',location.href);path.searchParams.set('match',doc.match_id);path.searchParams.set('decision',doc.decision_id);if(choice)path.searchParams.set('action',choice.action_id);
  $('#da-detail').innerHTML=`<section class="card decision-detail-card"><div class="decision-detail-heading"><div><span class="tiny-label">${esc(clock)} · EXACT GENERATOR SNAPSHOT</span><h2>${esc(label(bundle.request.actor_id))}</h2></div><span class="subtle-badge">${doc.assessment.candidate_count} supported choices</span></div><canvas class="decision-pitch" id="da-pitch" role="img" aria-label="Decision snapshot using the Replay pitch and team colours"></canvas><p class="legend decision-legend"><span><i class="home-dot"></i>Home</span><span><i class="away-dot"></i>Away</span><span>Dashed gold: selected route · Gold ring: current receiver · Diamond: predicted receiving point</span>${actual?' · Solid cream: matched historical type/recipient':''}</p>
  ${conditionsMarkup(doc.action_conditions,bundle.metadata)}
  <div class="decision-actions"><button class="button" id="da-jump" ${canJump?'':'disabled'}>Open in replay</button><a class="button ${choice?.eligible?'':'disabled-link'}" id="da-counterfactual" href="${esc(path.pathname+path.search)}" ${choice?.eligible?'':'aria-disabled="true"'}>Open counterfactual lab →</a><button class="button" id="da-export">Export analysis JSON</button></div>
  <p class="decision-note">${canJump?'Replay uses this same current match.':'No full animation for this moment. The exact decision snapshot remains available.'} Counterfactuals are available for every supported pass, carry and shot; they open separately.</p>
  <div class="decision-table-wrap"><table class="decision-table"><thead><tr><th>Rank</th><th>Candidate</th><th>Reason / opportunity</th><th>Main risk</th></tr></thead><tbody>${doc.public.candidates.filter(c=>c.eligible).map(c=>`<tr class="${c.action_id===selected?'selected':''}"><td>${c.rank??'—'}</td><td><button data-da-option="${esc(c.action_id)}">${esc(actionLabel(c,bundle.metadata))}</button><small>${c.eligible?'Supported':'Unsupported'}${options.find(a=>a.action_id===c.action_id)?.judgment.similar_to_best?' · Similar value':''}</small></td><td>${esc(c.opportunity)}</td><td>${esc(c.main_risk)}</td></tr>`).join('')}</tbody></table></div><details class="decision-reason"><summary>Excluded / unsupported choices (${doc.public.candidates.filter(c=>!c.eligible).length})</summary>${doc.public.candidates.filter(c=>!c.eligible).map(c=>`<p><strong>${esc(actionLabel(c,bundle.metadata))}</strong> · ${esc(c.main_risk)}</p>`).join('')}</details>
  <section class="decision-agent" id="da-agent" aria-label="Ask AI Coach"></section>
  <div class="decision-reason"><h3>${choice?esc(actionLabel(choice,bundle.metadata)):'No supported comparison'}</h3><p>${esc(choice?.judgment.reason||'This state is outside model support.')}</p><p>${esc(choice?.judgment.risk||'No inferred score.')}</p><p class="decision-note">Rules and two-step successors are hypotheses, not verified optimal play. Similar value uses a fixed 0.005 display tolerance, not a confidence interval.</p><details><summary>Evidence and model assumptions</summary>${doc.public.evidence.filter(e=>choice?.judgment.evidence_ids.includes(e.evidence_id)).map(e=>`<p><strong>${esc(e.kind)} · ${esc(e.evidence_id)}</strong><br>${esc(e.value)}</p>`).join('')}<p>${esc(choice?.judgment.assumptions.join(' · ')||'')}</p></details><details><summary>Historical choice · retrospective only</summary><button class="button" id="da-actual">Reveal historical choice</button><p id="da-actual-text">${actual?esc(actual.actual_action_id?`Historical type / recipient: ${actual.actual_action_id}. ${actual.resolution}`:actual.resolution):'Hidden. Historical outcomes are not scoring inputs.'}</p></details><details><summary>Agent-ready JSON and provenance</summary><p>All 30 features, branch assumptions, Q1/Q2 decomposition, Softmax weights, judgments and source IDs are available through the versioned diagnostics contract. The canonical public contract remains rank/text only.</p><p>${esc(doc.model.model_id)} · ${esc(doc.source.dataset_version)} · snapshot ${esc(doc.snapshot_id)}</p><p>Ask AI Coach uses the existing four-role team and this exact candidate set. Computed Q2 remains available if the model service is unavailable.</p><a href="contracts/decision-analysis/README.md">Integration contract</a></details></div></section>`;
  $('#da-jump').onclick=()=>jump(doc.snapshot.t_ms);
  $('#da-counterfactual').onclick=e=>{if(!choice?.eligible)e.preventDefault();save();};
  $('#da-export').onclick=()=>{const url=URL.createObjectURL(new Blob([JSON.stringify(doc,null,2)],{type:'application/json'})),a=document.createElement('a');a.href=url;a.download=doc.match_id+'-'+doc.decision_id+'-analysis.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
  $('#da-actual').onclick=async()=>{const token=requestId,cid=doc.candidate_set_id;try{const value=await api('actual',{request:bundle.request,candidate_set_id:cid},abort.signal);if(token!==requestId||cid!==doc.candidate_set_id)return;actual=value;renderDetail();}catch(e){if(e.name!=='AbortError')$('#da-actual-text').textContent=e.message;}};
  renderAgent();paint();
 }
 function renderAgent(){
  const panel=$('#da-agent');if(!panel||!doc||!bundle)return;
  const a=agent.state,busy=a.status==='loading',unsupported=!doc.public.candidates.some(c=>c.eligible);
  panel.innerHTML=`<h3>Ask AI Coach</h3><p class="decision-note">Coordinator · Attack · Defense · Reviewer. Answers cite this decision's evidence; AI cannot change Q2 ranking. Historical execution is not sent.</p>
   <form id="da-agent-form"><div class="decision-agent-options"><label>Audience<select id="da-agent-mode" ${busy||unsupported?'disabled':''}><option value="fan" ${a.mode==='fan'?'selected':''}>Fan</option><option value="analyst" ${a.mode==='analyst'?'selected':''}>Analyst</option></select></label><label>Language<select id="da-agent-language" ${busy||unsupported?'disabled':''}><option value="en" ${a.language==='en'?'selected':''}>English</option><option value="zh" ${a.language==='zh'?'selected':''}>中文</option></select></label></div>
   <label>Question about this decision<textarea id="da-agent-question" maxlength="900" required ${busy||unsupported?'disabled':''} placeholder="Why might a pass be preferable to carrying or shooting here?">${esc(a.question)}</textarea></label>
   <button class="button" type="submit" ${busy||unsupported?'disabled':''}>${busy?'Reviewing the evidence…':'Ask AI Coach'}</button></form>
   <p role="status" id="da-agent-status">${esc(unsupported?'No supported candidates. AI questions are unavailable for this snapshot.':a.status==='idle'?'Ready to ask. Q2 is computed without a model key.':a.status)}</p>
   <p class="decision-agent-answer" id="da-agent-answer">${esc(a.answer||a.error||'')}</p>
   ${a.evidence.length?`<details open><summary>Cited evidence (${a.evidence.length})</summary>${a.evidence.map(e=>`<p><strong>${esc(e.evidence_id)} · ${esc(e.kind)}</strong><br>${esc(e.value)}</p>`).join('')}</details>`:''}
   <details><summary>Agent trace and candidate binding</summary><p>${esc(doc.snapshot_id)} · ${esc(doc.candidate_set_id)}</p><pre>${esc(JSON.stringify(a.trace,null,2))}</pre></details>`;
  $('#da-agent-question').oninput=e=>{a.question=e.target.value;};
  $('#da-agent-mode').onchange=e=>{a.mode=e.target.value;};
  $('#da-agent-language').onchange=e=>{a.language=e.target.value;};
  $('#da-agent-form').onsubmit=e=>{e.preventDefault();agent.ask();};
 }
 async function select(row){
  if(!row)return;const token=++requestId,rev=epoch;current=row.decision_id;doc=bundle=null;actual=null;selected=null;agent.clear();decisionAbort.abort();decisionAbort=new AbortController();
  $('#da-detail').innerHTML='<p class="empty" role="status">Computing current-state comparison…</p>';
  $('#da-list').querySelectorAll('[data-da-decision]').forEach(b=>b.classList.toggle('selected',b.dataset.daDecision===current));
  const url=new URL(location.href);url.searchParams.set('decision',current);history.replaceState(null,'',url);
  try{
   const next=await api('context?match_id='+encodeURIComponent(context.metadata.match_id)+'&decision_id='+encodeURIComponent(current),undefined,decisionAbort.signal);
   const value=await api('analyze',next.request,decisionAbort.signal);
   if(token!==requestId||rev!==epoch)return;
   if(value.match_id!==context.metadata.match_id||value.snapshot_id!==next.snapshot.snapshot_id||value.data_version!==next.snapshot.data_version)throw Error('Stale analysis discarded.');
   validateDecisionDocument(value,next);doc=value;bundle=next;selected=doc.assessment.recommended_action_id;
   const requestedAction=new URL(location.href).searchParams.get('action');if(doc.candidates.some(c=>c.action_id===requestedAction&&c.eligible))selected=requestedAction;
   agent.bind(bundle,doc);renderDetail();
  }catch(e){if(token===requestId&&rev===epoch&&e.name!=='AbortError')$('#da-detail').innerHTML=`<p class="empty" role="status">${esc(e.message)}</p>`;}
 }
 function renderList(){
  if(!index)return;const rows=filterDecisionRecords(index.records,filters(),index.representative_ids,index.largest_ids);
  $('#da-count').textContent=rows.length.toLocaleString()+' moments';$('#da-more').hidden=rows.length<=listStart+page;$('#da-earlier').hidden=listStart===0;$('#da-window').textContent=rows.length?`Showing ${listStart+1}–${Math.min(rows.length,listStart+page)} of ${rows.length} decisions`:'';
  $('#da-list').innerHTML=rows.slice(listStart,listStart+page).map(r=>`<button class="decision-row ${current===r.decision_id?'selected':''}" data-da-decision="${esc(r.decision_id)}"><time>${esc(context.clock(r.t_ms,r.period))}</time><span><strong>${esc(label(r.actor_id))}</strong><small>${esc(r.kind)} · ${esc(r.category)} · ${esc(['Build-up','Midfield','Attack'][r.zone])}</small></span></button>`).join('')||'<p class="empty">No decisions match these filters. Try All decisions or another player.</p>';
  if(!rows.some(r=>r.decision_id===current)){if(rows.length)select(rows[0]);else{requestId++;agent.clear();decisionAbort.abort();doc=bundle=null;current=null;$('#da-detail').innerHTML='<p class="empty">No decision selected.</p>';}}
 }
 async function load(){
  if(!shown||!context||index||loading)return;const rev=epoch;loading=true;$('#da-status').textContent='Loading current-generator decision index…';
  try{
   const value=await api('index?match_id='+encodeURIComponent(context.metadata.match_id),undefined,abort.signal);if(rev!==epoch)return;
   if(value.match_id!==context.metadata.match_id||value.source_dataset!=='league')throw Error('Wrong source data or analysis not built.');index=value;
   const s=index.summary;$('#da-summary').innerHTML=[['Available snapshots',s.covered],['Analyzable decisions',s.analyzable],['Players with decisions',s.players],['Representative players',s.representative_players]].map(([n,v])=>`<article><span>${n}</span><strong>${Number(v).toLocaleString()}</strong></article>`).join('');
   $('#da-status').textContent='Current match and decision source verified. No language model is required.';
   const url=new URL(location.href),requested=pendingDecision||(url.searchParams.get('match')===context.metadata.match_id?url.searchParams.get('decision'):null);
   if(requested&&index.records.some(r=>r.decision_id===requested)){current=requested;for(const k of ['team','player','kind'])$('#da-'+k).value='';$('#da-scope').value='all';page=30;listStart=Math.max(0,index.records.findIndex(r=>r.decision_id===requested)-10);}
   pendingDecision=null;renderList();if(requested&&current===requested)select(index.records.find(r=>r.decision_id===requested));
  }catch(e){if(rev===epoch&&e.name!=='AbortError')$('#da-status').textContent=e.message;}
  finally{if(rev===epoch)loading=false;}
 }
 for(const key of ['team','player','kind','scope'])$('#da-'+key).onchange=()=>{page=30;listStart=0;save();renderList();};
 $('#da-more').onclick=()=>{page+=30;renderList();};$('#da-earlier').onclick=()=>{listStart=Math.max(0,listStart-30);page=30;renderList();};
 container.addEventListener('click',e=>{const row=e.target.closest('[data-da-decision]');if(row)select(index.records.find(r=>r.decision_id===row.dataset.daDecision));const option=e.target.closest('[data-da-option]');if(option&&doc){selected=option.dataset.daOption;const url=new URL(location.href);url.searchParams.set('action',selected);history.replaceState(null,'',url);renderDetail();}});
 new ResizeObserver(()=>{if(shown)paint();}).observe(container);
 function clear(){epoch++;requestId++;agent.clear();decisionAbort.abort();abort.abort();abort=new AbortController();index=doc=bundle=null;context=null;current=selected=actual=null;pendingDecision=null;loading=false;$('#da-list').replaceChildren();$('#da-summary').replaceChildren();$('#da-detail').innerHTML='<p class="empty">Select a current-match decision.</p>';}
 return {clear,openDecision(id){pendingDecision=id;if(index){const row=index.records.find(r=>r.decision_id===id);if(row){for(const k of ['team','player','kind'])$('#da-'+k).value='';$('#da-scope').value='all';current=id;page=30;listStart=Math.max(0,index.records.findIndex(r=>r.decision_id===id)-10);renderList();select(row);pendingDecision=null;}}else load();},show(value){shown=value;if(value){load();paint();}},refreshReplayAvailability(){if(shown&&doc)renderDetail();},setMatch(value){clear();context=value;page=30;listStart=0;$('#da-team').innerHTML='<option value="">Both teams</option>'+value.metadata.teams.map(t=>`<option value="${t.team_id}">${esc(t.name)}</option>`).join('');$('#da-player').innerHTML='<option value="">All players</option>'+value.metadata.players.map(p=>`<option value="${p.player_id}">${esc(playerLabel(value.metadata,p.player_id))}</option>`).join('');for(const k of ['kind','scope'])$('#da-'+k).value=k==='scope'?'representative':'';try{const saved=JSON.parse(sessionStorage.getItem('decision-filters:'+value.metadata.match_id));if(saved)for(const k of ['team','player','kind','scope'])$('#da-'+k).value=saved[k]|| (k==='scope'?'representative':'');}catch{}load();}};
}
