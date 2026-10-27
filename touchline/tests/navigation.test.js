import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {resolveView,viewURL} from '../navigation.js';
import {decisionURL} from '../player-identity.js';

test('Standalone and legacy decision links resolve to one view without losing bound identity',()=>{
  for(const query of ['view=decisions','view=stats&analysis=decisions']){
    const before=new URL('http://localhost/index.html?'+query+'&match=PL26-W03-EVE-CRY&decision=d001709&action=pass%3AH10');
    const view=resolveView(before.searchParams);assert.equal(view,'decisions');
    const after=viewURL(before.href,view);
    assert.equal(after.searchParams.get('view'),'decisions');assert.equal(after.searchParams.has('analysis'),false);
    for(const field of ['match','decision','action'])assert.equal(after.searchParams.get(field),before.searchParams.get(field));
  }
});
test('Analysis remains reports; non-implemented video mode does not masquerade as a working view',()=>{
  assert.equal(resolveView('view=stats'),'stats');assert.equal(resolveView('view=stats&analysis=report'),'stats');
  for(const view of ['home','overview','replay','lineup','squads','settings'])assert.equal(resolveView('view='+view),view);
  assert.equal(resolveView('view=video','home'),'home');assert.throws(()=>viewURL('http://localhost/','video'),/Unknown/);
});
test('All current decision deep links use the independent route',()=>{
  const url=new URL(decisionURL('m','d','carry:left'),'http://localhost/');
  assert.equal(url.searchParams.get('view'),'decisions');assert.equal(url.searchParams.has('analysis'),false);
  assert.equal(url.searchParams.get('action'),'carry:left');
});
test('Main document no longer has nested analysis tabs or an active Public Demo/Video placeholder route',()=>{
  const html=fs.readFileSync(new URL('../index.html',import.meta.url),'utf8');
  assert.ok(!html.includes('data-analysis-tab'));assert.ok(!html.includes('analysis-subtabs'));
  assert.match(html,/id="nav-decision-analysis" data-view="decisions" href="index.html\?view=decisions"/);
  assert.ok(!html.includes('public-demo/'));assert.match(html,/href="video-analysis.html">Video Analysis<\/a>/);
  assert.match(html,/<section id="decision-analysis" hidden aria-label="Decision Analysis">/);
  assert.ok(!html.includes('aria-labelledby="decisions-tab"'));
  assert.match(html,/<nav class="workspace-mobile-links" aria-label="Workspace">/);
});
