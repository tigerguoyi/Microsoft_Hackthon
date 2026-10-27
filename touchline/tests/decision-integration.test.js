import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {filterDecisionRecords,conditionsMarkup} from '../decision-analysis-view.js';
import {pitchGeometry,renderPitch} from '../pitch-renderer.js';
test('Filter intersection preserves source records and separates representatives/losses/coverage',()=>{
 const rows=[{decision_id:'a',team_id:'HOME',actor_id:'H01',kind:'pass',analyzable:true},{decision_id:'b',team_id:'AWAY',actor_id:'A02',kind:'shot',analyzable:false}];
 assert.deepEqual(filterDecisionRecords(rows,{scope:'all',team:'HOME'}),[rows[0]]);
 assert.deepEqual(filterDecisionRecords(rows,{scope:'representative'},['a'],['b']),[rows[0]]);
 assert.deepEqual(filterDecisionRecords(rows,{scope:'coverage'}),[rows[1]]);
 assert.deepEqual(filterDecisionRecords(rows,{scope:'all',kind:'shot',player:'H01'}),[]);
});
test('Replay and Decision share one renderer, palette, numbered identities and geometry',()=>{
 const replay=fs.readFileSync(new URL('../app.js',import.meta.url),'utf8'),decision=fs.readFileSync(new URL('../decision-analysis-view.js',import.meta.url),'utf8'),lab=fs.readFileSync(new URL('../decision-counterfactual.js',import.meta.url),'utf8');
 assert.ok([replay,decision,lab].every(s=>s.includes("from './pitch-renderer.js")));
 const fills=[],numbers=[],ctx=new Proxy({fillText:(...args)=>numbers.push(args[0])},{set(o,k,v){if(k==='fillStyle')fills.push(v);o[k]=v;return true;},get(o,k){return o[k]||(()=>{});}}),canvas={clientWidth:700,clientHeight:450,width:0,height:0,getContext:()=>ctx};
 renderPitch(canvas,{players:[['H01',5,34,0,0],['A01',100,34,0,0]],ball:[6,34,0,0,0,0],ball_owner_id:'H01'},{metadata:{players:[{player_id:'H01',team_id:'HOME',jersey_number:7},{player_id:'A01',team_id:'AWAY',jersey_number:1}]}});
 assert.ok(fills.includes('#426e57')&&fills.includes('#47745c')&&fills.includes('#ee8b5a')&&fills.includes('#83a3e0'));assert.deepEqual(numbers,[7,1]);
 assert.equal(pitchGeometry(700,450).scale,Math.min((700-42)/105,(450-69)/68));
});
test('Condition rendering preserves unknown orientation and escapes identity labels',()=>{
 const html=conditionsMarkup({speed_mps:0,speed_kmh:0,movement_heading_deg:null,movement_label:'Stationary / slow',nearest_opponent:{player_id:'A01',distance_m:1},under_pressure_3m:true,opponents_within_5m:1,ball_distance_m:.35},{players:[{player_id:'A01',name:'<unsafe>'}]});
 assert.ok(html.includes('Player action conditions')&&html.includes('&lt;unsafe&gt;')&&html.includes('not body orientation'));assert.ok(!html.includes('<unsafe>'));
});
