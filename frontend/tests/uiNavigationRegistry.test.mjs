import {readFile} from 'node:fs/promises';
import assert from 'node:assert/strict';
import test from 'node:test';
import ts from 'typescript';

const source = await readFile(new URL('../src/navigationRegistry.ts', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022}}).outputText;
const nav = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`);

test('every legacy destination keeps its ID and resolves independently of its public label', () => {
  const legacy = ['Home','Attention','Graph','Messages','Handoffs','Meta-harness','Events','Artifacts','Memory','Workspaces','Agents','Registry','Policies','Guardrails','Communication','Approvals','Runtimes','Execution log','Settings'];
  assert.equal(new Set(nav.NAVIGATION_REGISTRY.map(x => x.id)).size, 20);
  assert.deepEqual([...nav.VIEW_IDS].sort(), [...legacy, 'Advanced'].sort());
  for (const id of legacy) assert.equal(nav.resolveNavigationId(id), id);
  assert.equal(nav.resolveNavigationId('Conversations'), 'Meta-harness');
  assert.equal(nav.resolveNavigationId('Message history'), 'Messages');
  assert.equal(nav.resolveNavigationId('Runtime administration'), 'Runtimes');
  assert.notEqual(nav.resolveNavigationId('Conversations'), 'Messages');
  for (const input of ['Harnesses','Sessions','Executions','Monitoring','__proto__','',null,{},42]) assert.equal(nav.resolveNavigationId(input), null);
});

test('sidebar has exactly four primary destinations and one secondary Advanced; Attention is utility', () => {
  assert.deepEqual(nav.PRIMARY_NAVIGATION.map(x => [x.id,x.label]), [['Home','Home'],['Meta-harness','Conversations'],['Graph','Graph'],['Artifacts','Artifacts']]);
  assert.deepEqual(nav.SECONDARY_NAVIGATION.map(x => x.id), ['Advanced']);
  assert.equal(nav.getNavigationEntry('Attention').section, 'utility');
  assert.equal(nav.getNavigationEntry('Attention').group, undefined);
  assert.ok(!nav.PRIMARY_NAVIGATION.some(x => x.id === 'Attention'));
});

test('four purpose groups cover every advanced destination exactly once without utility duplication', () => {
  const groups = nav.getAdvancedGroups({memoryEnabled:true});
  assert.deepEqual(groups.map(x => x.id), ['agents-execution','policies-control','history-diagnostics','system-data']);
  assert.deepEqual(groups.map(x => x.entries.map(e => e.id)), [
    ['Agents','Runtimes','Registry','Communication'], ['Policies','Guardrails','Approvals'],
    ['Messages','Handoffs','Events','Execution log','Workspaces'], ['Memory','Settings'],
  ]);
  for (const entry of nav.NAVIGATION_REGISTRY) assert.ok(entry.description.length > 10);
});

test('Memory visibility follows feature state without removing its legacy ID or enabling authorization', () => {
  const off = nav.getAdvancedGroups({memoryEnabled:false}).flatMap(x => x.entries);
  const on = nav.getAdvancedGroups({memoryEnabled:true}).flatMap(x => x.entries);
  assert.ok(!off.some(x => x.id === 'Memory'));
  assert.ok(on.some(x => x.id === 'Memory'));
  assert.equal(nav.resolveNavigationId('Memory'), 'Memory');
  assert.equal(nav.resolveNavigationId('Shared memory'), 'Memory');
  assert.equal(nav.isNavigationVisible(nav.getNavigationEntry('Approvals'), {memoryEnabled:false}), true);
  assert.equal(nav.getNavigationEntry('Memory').feature, 'memory');
});

test('breadcrumb and selected sidebar section retain exact destination and public label', () => {
  assert.deepEqual(nav.getNavigationBreadcrumb('Runtimes'), [{id:'Advanced',label:'Advanced'},{id:'Advanced',label:'Agents and execution'},{id:'Runtimes',label:'Runtime administration'}]);
  assert.equal(nav.getNavigationSectionId('Runtimes'), 'Advanced');
  assert.deepEqual(nav.getNavigationBreadcrumb('Meta-harness'), [{id:'Meta-harness',label:'Conversations'}]);
  assert.equal(nav.getNavigationSectionId('Meta-harness'), 'Meta-harness');
  assert.equal(nav.getNavigationSectionId('Attention'), 'Attention');
});
