import {validateDecisionDocument} from './player-identity.js';
import {renderPitch} from './pitch-renderer.js?v=unified-1';
import {api,esc,actionLabel,conditionsMarkup} from './decision-analysis-view.js?v=unified-1';
const $=s=>document.querySelector(s),params=new URLSearchParams(location.search),match=params.get('match'),decision=params.get('decision');
let context,doc,result=null,animation=null,token=0,controller=new AbortController();
const back=new URL('/',location.href);back.search=new URLSearchParams({view:'stats',analysis:'decisions',match:match||'',decision:decision||''});$('#cf-back').href=back.pathname+back.search;
function stop(){if(animation!==null)cancelAnimationFrame(animation);animation=null;$('#cf-play').textContent='Play hypothesis';}
function choice(){return doc?.candidates.find(c=>c.action_id===$('#cf-action').value);}
function paint(frame=null){if(!doc||!context)return;const c=choice();renderPitch($('#cf-pitch'),frame?{...doc.snapshot.frame,...frame}:doc.snapshot.frame,{metadata:context.metadata,selected:context.request.actor_id,route:c?{start:doc.snapshot.frame.ball,target:c.target,recipient_id:c.type==='pass'?c.recipient_id:null}:null});}
function changed(){token++;controller.abort();controller=new AbortController();stop();result=null;$('#cf-title').textContent='Observed decision-time snapshot';for(const k of ['scenario','play','reset','time','export'])$('#cf-'+k).disabled=true;$('#cf-time').value=0;const c=choice();if(c)back.searchParams.set('action',c.action_id);else back.searchParams.delete('action');$('#cf-back').href=back.pathname+back.search;$('#cf-evidence').innerHTML=c?`<p><strong>${esc(c.judgment.reason)}</strong></p><p>${esc(c.judgment.risk)}</p><p class="decision-note">${esc(c.judgment.assumptions.join(' · '))}</p>`:'';$('#cf-compute').disabled=!c?.judgment.counterfactual_available;$('#cf-playback').textContent='Observed snapshot restored. Compute the selected action to explore its hypotheses.';paint();}
function show(){if(!result)return;const scenario=result.scenarios[Number($('#cf-scenario').value)],f=scenario.frames[Number($('#cf-time').value)];$('#cf-title').textContent='Counterfactual playback · separate timeline';paint(f);$('#cf-playback').textContent=`${scenario.id} · +${f.elapsed_s.toFixed(2)} s · ${Number($('#cf-time').value)===scenario.frames.length-1?'Terminal outcome: '+scenario.outcome:'Hypothesis in progress'}. Scenario counts are not probabilities.`;}
$('#cf-action').onchange=changed;
$('#cf-compute').onclick=async()=>{changed();const mine=token,action=$('#cf-action').value;$('#cf-compute').disabled=true;$('#cf-status').textContent='Computing the bound short hypothesis…';try{
 const value=await api('counterfactual',{request:context.request,candidate_set_id:doc.candidate_set_id,action_id:action},controller.signal);
 if(mine!==token||action!==$('#cf-action').value)return;if(value.snapshot_id!==doc.snapshot_id||value.candidate_set_id!==doc.candidate_set_id)throw Error('Stale counterfactual discarded.');result=value;
 $('#cf-scenario').innerHTML=value.scenarios.map((s,i)=>`<option value="${i}">${esc(s.id)} · ${s.reaction_s} s reaction</option>`).join('');$('#cf-time').max=value.scenarios[0].frames.length-1;$('#cf-time').value=0;
 for(const k of ['scenario','play','reset','time','export'])$('#cf-'+k).disabled=false;$('#cf-status').textContent='Hypothesis ready. Actual match data and ranking are unchanged.';show();
 }catch(e){if(mine===token&&e.name!=='AbortError')$('#cf-status').textContent=e.message;}finally{if(mine===token)$('#cf-compute').disabled=false;}};
$('#cf-scenario').onchange=()=>{stop();$('#cf-time').max=result.scenarios[Number($('#cf-scenario').value)].frames.length-1;$('#cf-time').value=0;show();};
$('#cf-time').oninput=()=>{stop();show();};$('#cf-reset').onclick=()=>{stop();$('#cf-time').value=0;$('#cf-title').textContent='Observed decision-time snapshot';paint();$('#cf-playback').textContent='Observed snapshot restored. No match records were changed.';};
$('#cf-play').onclick=()=>{if(!result)return;if(animation!==null){stop();return;}if(Number($('#cf-time').value)>=Number($('#cf-time').max))$('#cf-time').value=0;$('#cf-play').textContent='Pause hypothesis';const start=performance.now()-Number($('#cf-time').value)*50;const tick=now=>{const max=Number($('#cf-time').max);$('#cf-time').value=Math.min(max,Math.floor((now-start)/50));show();if(Number($('#cf-time').value)<max)animation=requestAnimationFrame(tick);else stop();};animation=requestAnimationFrame(tick);};
$('#cf-export').onclick=()=>{const url=URL.createObjectURL(new Blob([JSON.stringify(result,null,2)],{type:'application/json'})),a=document.createElement('a');a.href=url;a.download=match+'-'+decision+'-'+result.action_type+'-hypothesis.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
new ResizeObserver(()=>{if(result&&$('#cf-title').textContent.startsWith('Counterfactual'))show();else paint();}).observe($('#cf-pitch'));
document.addEventListener('visibilitychange',()=>{if(document.hidden)stop();});
try{
 if(!match||!decision)throw Error('Open this page from a registered decision in Analysis.');context=await api('context?match_id='+encodeURIComponent(match)+'&decision_id='+encodeURIComponent(decision));doc=await api('analyze',context.request);
 if(doc.match_id!==match||doc.snapshot_id!==context.snapshot.snapshot_id)throw Error('Mismatched decision context.');validateDecisionDocument(doc,context);
 $('#cf-conditions').innerHTML=conditionsMarkup(doc.action_conditions,context.metadata);const candidates=doc.candidates.filter(c=>c.judgment.counterfactual_available);
 $('#cf-action').innerHTML=candidates.map(c=>`<option value="${esc(c.action_id)}">#${c.rank} · ${esc(actionLabel(c,context.metadata))}</option>`).join('');$('#cf-action').disabled=!candidates.length;
 if(candidates.some(c=>c.action_id===params.get('action')))$('#cf-action').value=params.get('action');changed();$('#cf-status').textContent=candidates.length?'Registered current-generator snapshot and model verified.':'No supported action at this decision; return to Analysis.';
}catch(e){$('#cf-status').textContent=e.message;}
