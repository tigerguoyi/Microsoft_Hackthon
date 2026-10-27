import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {resolvePlayer,describeAction,candidateIdentityIssues,validateDecisionDocument,decisionURL} from '../player-identity.js';
import {goalTimeline,scoreAt,scoreContext,validateMatchBundle} from '../score-context.js';
import {createDecisionAgent} from '../decision-agent.js';
const read=p=>JSON.parse(fs.readFileSync(new URL(p,import.meta.url),'utf8'));
const meta=read('../data/league/matches/PL26-W03-EVE-CRY/metadata.json');
const raw=fs.readFileSync(new URL('../data/league/matches/PL26-W03-EVE-CRY/decisions.jsonl',import.meta.url),'utf8').trim().split('\n').map(JSON.parse);

test('Ivory H10 and Highridge A08 resolve from metadata rather than ID digits',()=>{
  const home=resolvePlayer(meta,'H10'),away=resolvePlayer(meta,'A08');
  assert.equal(home.jersey_number,11);assert.equal(home.club_id,'EVE');
  assert.equal(describeAction({type:'pass',action_id:'pass:H10'},meta),'Pass to EVE #11 · Ivory Player 19');
  assert.equal(away.jersey_number,10);assert.equal(away.club_id,'CRY');
  assert.match(describeAction({type:'pass',action_id:'pass:A08'},meta),/^Pass to CRY #10 · Highridge Player 15$/);
  assert.equal(resolvePlayer(meta,'H99').valid,false);
});
test('Pass identity rejects opponents, self, absent/substituted players and false targets',()=>{
  const f=raw[0].snapshot,p=f.players.find(p=>p[0]==='H08');
  const c={type:'pass',action_id:'pass:H08',recipient_id:'H08',target:[p[1]+.25*p[3],p[2]+.25*p[4]]};
  assert.deepEqual(candidateIdentityIssues(c,f,meta,'H10'),[]);
  assert.ok(candidateIdentityIssues({...c,action_id:'pass:A08'},f,meta,'H10').length);
  assert.ok(candidateIdentityIssues({...c,action_id:'pass:H10',recipient_id:'H10'},f,meta,'H10').length);
  assert.ok(candidateIdentityIssues({...c,target:[0,0]},f,meta,'H10').length);
  assert.ok(candidateIdentityIssues(c,{...f,players:f.players.filter(p=>p[0]!=='H08')},meta,'H10').length);
  assert.ok(candidateIdentityIssues({...c,recipient_id:'H07'},f,meta,'H10').length);
});
test('Score follows goal availability, including exact goal boundary and rewinding',()=>{
  const goals=goalTimeline([{type:'shot',outcome:'goal',team_id:'HOME',available_at_ms:20,sequence:2},
    {type:'shot',outcome:'goal',team_id:'AWAY',available_at_ms:10,sequence:1}]);
  assert.deepEqual(scoreAt(goals,9),[0,0]);assert.deepEqual(scoreAt(goals,10),[0,1]);
  assert.deepEqual(scoreAt(goals,20),[1,1]);assert.deepEqual(scoreAt(goals,19),[0,1]);
  assert.equal(scoreContext({live:true,clock:'69:30',final:[1,1]}),'Replay score at 69:30 · Final score 1–1 (FT)');
  assert.equal(scoreContext({live:false,final:[1,1]}),'Final score 1–1 · FT');
});
test('Match load fails closed for mixed identity, final score and incorrect preview frames',()=>{
  const fixture={match_id:'m',score:[1,0]},metadata={match_id:'m',duration_ms:20};
  const summary={match_id:'m',final_score:[1,0]},preview={match_id:'m',frames:[{t_ms:9,score:[0,0]},{t_ms:10,score:[1,0]}]};
  const events=[{match_id:'m',type:'shot',outcome:'goal',team_id:'HOME',available_at_ms:10,sequence:1}];
  assert.equal(validateMatchBundle(fixture,metadata,summary,preview,events).length,1);
  assert.throws(()=>validateMatchBundle(fixture,{...metadata,match_id:'other'},summary,preview,events),/identity/);
  assert.throws(()=>validateMatchBundle({...fixture,score:[2,0]},metadata,summary,preview,events),/Final score/);
  assert.throws(()=>validateMatchBundle(fixture,metadata,summary,{...preview,frames:[{t_ms:9,score:[1,0]}]},events),/Preview score/);
});
function binding(id){
  const publicCandidates=[{action_id:'carry:forward',type:'carry',rank:1,eligible:true}];
  const snapshot={snapshot_id:id,match_id:'m',data_version:'v',frame:raw[0].snapshot};
  const bundle={snapshot,metadata:meta,request:{match_id:'m',snapshot_id:id,t_ms:10,actor_id:'H10',profile:{profile_version:'sim-1'},mode:'analyst',language:'en',question:'Compare'}};
  const doc={snapshot,match_id:'m',snapshot_id:id,data_version:'v',candidate_set_id:`set-${id}`,public:{candidates:publicCandidates,evidence:[{evidence_id:'e',kind:'computed',value:'A supported fact'}]},candidates:publicCandidates};
  return {bundle,doc};
}
function response(doc,text='Reviewed answer'){
  return {snapshot_id:doc.snapshot_id,data_version:doc.data_version,candidate_set_id:doc.candidate_set_id,status:'ready',candidates:structuredClone(doc.public.candidates),
    explanation:{text,cited_evidence_ids:['e']},agent_trace:[{agent:'reviewer',tool:'check_evidence',ok:true}]};
}
test('Agent receives only canonical request and candidate binding; no historical outcomes',async()=>{
  const {bundle,doc}=binding('one');doc.actual_outcome='goal';doc.retrospective={future_goal:true};
  let sent;const agent=createDecisionAgent(async(path,body)=>{sent={path,body};return response(doc);});
  agent.bind(bundle,doc);await agent.ask('Compare these choices','analyst','zh');
  assert.equal(sent.path,'agents');assert.equal(sent.body.candidate_set_id,doc.candidate_set_id);
  assert.equal(sent.body.request.mode,'analyst');assert.equal(sent.body.request.language,'zh');
  assert.equal(JSON.stringify(sent).includes('actual_outcome'),false);assert.equal(JSON.stringify(sent).includes('future_goal'),false);
  assert.equal(agent.state.answer,'Reviewed answer');assert.equal(agent.state.evidence[0].evidence_id,'e');
  assert.equal(agent.state.trace[0].agent,'reviewer');
});
test('Slow Agent response from another decision cannot overwrite the current answer, even if abort is ignored',async()=>{
  const a=binding('one'),b=binding('two');let resolveOld;
  const agent=createDecisionAgent((path,body)=>body.candidate_set_id===a.doc.candidate_set_id?new Promise(resolve=>{resolveOld=resolve;}):Promise.resolve(response(b.doc,'New answer')));
  agent.bind(a.bundle,a.doc);const old=agent.ask('Old question');agent.bind(b.bundle,b.doc);
  assert.equal(agent.state.answer,null);await agent.ask('New question');resolveOld(response(a.doc,'Stale answer'));await old;
  assert.equal(agent.state.answer,'New answer');agent.clear();assert.equal(agent.state.answer,null);
});
test('Agent unavailable, stale candidate, changed rank and uncited evidence never replace deterministic analysis',async()=>{
  const {bundle,doc}=binding('one');const before=structuredClone(doc.public.candidates);
  for(const change of [v=>({...v,candidate_set_id:'old'}),v=>({...v,candidates:[{...v.candidates[0],rank:2}]}),
    v=>({...v,explanation:{text:'bad',cited_evidence_ids:['foreign']}})]){
    const agent=createDecisionAgent(async()=>change(response(doc)));agent.bind(bundle,doc);await agent.ask('Why?');
    assert.equal(agent.state.status,'error');assert.equal(agent.state.answer,null);assert.deepEqual(doc.public.candidates,before);
  }
  const agent=createDecisionAgent(async()=>({...response(doc),status:'model_unavailable',explanation:null}));agent.bind(bundle,doc);await agent.ask('Why?');
  assert.equal(agent.state.status,'model_unavailable');assert.match(agent.state.error,/Q2 comparison remains/);assert.deepEqual(doc.public.candidates,before);
});
test('Diagnostic document and deep links retain exact match, snapshot and candidate identities',()=>{
  const {bundle,doc}=binding('one');validateDecisionDocument(doc,bundle);
  assert.throws(()=>validateDecisionDocument({...doc,match_id:'other'},bundle),/mismatched/);
  const q=new URL(decisionURL('PL26-W03-EVE-CRY','d000001','pass:H10'),'http://localhost/').searchParams;
  assert.equal(q.get('match'),'PL26-W03-EVE-CRY');assert.equal(q.get('decision'),'d000001');assert.equal(q.get('action'),'pass:H10');
});
test('Unsupported terminal snapshots do not invoke an Agent',async()=>{
  const {bundle,doc}=binding('ended');doc.public.candidates=[];let called=false;
  const agent=createDecisionAgent(async()=>{called=true;});agent.bind(bundle,doc);await agent.ask('Why?');
  assert.equal(called,false);assert.equal(agent.state.status,'unsupported');assert.match(agent.state.error,/No supported/);
});
