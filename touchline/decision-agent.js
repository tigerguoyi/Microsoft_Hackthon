// UI lifecycle only. The existing server owns roles, provider, budget and review.
export function createDecisionAgent(api,onChange=()=>{}) {
  const state={question:'',mode:'fan',language:'en',status:'idle',answer:null,trace:[],evidence:[],error:''};
  let current=null,epoch=0,controller=null;
  function clear() {
    epoch++;controller?.abort();controller=null;current=null;
    Object.assign(state,{question:'',status:'idle',answer:null,trace:[],evidence:[],error:''});onChange(state);
  }
  function bind(bundle,doc) {clear();if(bundle&&doc)current={bundle,doc};}
  async function ask(question=state.question,mode=state.mode,language=state.language) {
    if (!current) return;
    if(!current.doc.public.candidates.some(c=>c.eligible)){state.status='unsupported';state.error='No supported candidate comparison for this snapshot.';onChange(state);return;}
    if (!question.trim() || !['fan','analyst'].includes(mode) || !['en','zh'].includes(language)) return;
    controller?.abort();controller=new AbortController();const token=++epoch,{bundle,doc}=current;
    const request=JSON.parse(JSON.stringify({...bundle.request,question:question.trim(),mode,language}));
    Object.assign(state,{question,mode,language,status:'loading',answer:null,trace:[],evidence:[],error:''});onChange(state);
    try {
      const value=await api('agents',{request,candidate_set_id:doc.candidate_set_id},controller.signal);
      if(token!==epoch||current?.doc!==doc)return;
      if(value.snapshot_id!==doc.snapshot_id||value.candidate_set_id!==doc.candidate_set_id||value.data_version!==doc.data_version)
        throw Error('Stale Agent response discarded. Re-analyze this decision.');
      const signature=rows=>JSON.stringify(rows.map(c=>[c.action_id,c.rank,c.eligible]));
      if(signature(value.candidates)!==signature(doc.public.candidates))throw Error('Agent response changed the computed ranking; discarded.');
      const ids=new Set((doc.public.evidence||[]).map(e=>e.evidence_id));
      if((value.explanation?.cited_evidence_ids||[]).some(id=>!ids.has(id)))throw Error('Agent cited evidence outside this candidate set.');
      Object.assign(state,{status:value.status,answer:value.explanation?.text||null,trace:value.agent_trace||[],
        evidence:(doc.public.evidence||[]).filter(e=>value.explanation?.cited_evidence_ids?.includes(e.evidence_id)),
        error:!value.explanation?.text?'AI explanation is unavailable. The deterministic Q2 comparison remains available.':''});
    } catch(error) {
      if(token!==epoch||error.name==='AbortError')return;
      Object.assign(state,{status:'error',error:error.message,answer:null,trace:[],evidence:[]});
    }
    if(token===epoch)onChange(state);
  }
  return {state,bind,clear,ask};
}
