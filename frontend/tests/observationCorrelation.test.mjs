import assert from 'node:assert/strict';
import {existsSync, readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import test from 'node:test';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import ts from 'typescript';

// Compile the real components and local modules, without a browser or network.
const require = createRequire(import.meta.url), modules = new Map();
function load(url) {
  const filename = fileURLToPath(url);
  if (modules.has(filename)) return modules.get(filename).exports;
  const module = {exports: {}};
  modules.set(filename, module);
  const source = ts.transpileModule(readFileSync(filename, 'utf8'), {fileName: filename, compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX,
  }}).outputText;
  const localRequire = name => {
    if (!name.startsWith('.')) return require(name);
    const candidate = ['.ts', '.tsx'].map(extension => new URL(name + extension, url)).find(path => existsSync(path));
    assert.ok(candidate, `Local module exists: ${name}`);
    return load(candidate);
  };
  new Function('require', 'module', 'exports', source)(localRequire, module, module.exports);
  return module.exports;
}
const {ExternalObservationMetadata, ExternalAgentActivity} = load(new URL('../src/components/ExternalObservations.tsx', import.meta.url));
const {ObservationReader} = load(new URL('../src/observationReader.ts', import.meta.url));
const {attentionTarget, readAttentionReference} = load(new URL('../src/attentionNavigation.ts', import.meta.url));
const fixture = () => ({observed_instance_id: 'instance', source_id: 'source', generation: 2,
  agent_id: 'agent', workspace_id: 'workspace', source_revision: 3, source_kind: 'custom',
  external_instance_ref: 'source context', observational_only: true, freshness: 'current', activity_state: 'working',
  source_last_received_at: null, source_continuity: 'recent', last_report: null,
  canonical_session_ref: {server_id: 'server', executor_id: 'executor', session_id: 'canonical-session',
    open_operation_id: 'open-operation', session_owner_generation: 7, stream_epoch: 'stream'},
  canonical_observation: {correlation_revision: 4, verified_at: '2030-01-01T10:00:00Z',
    provenance: {external_binding_provenance: 'operator_attested_external_binding', native_birth_provenance: 'machine_checked_native_birth'},
    session_lifecycle_state: 'READY', precedence: 'canonical_core_facts',
    last_received_receipt: {status: 'verified', operation_id: 'received-operation', action: 'runtime.send', stage: 'SUCCEEDED',
      receipt_revision: 8, received_at: '2030-01-01T10:01:00Z', provenance: 'core_committed'}},
});
const render = (item, props = {}) => renderToStaticMarkup(React.createElement(ExternalObservationMetadata, {item, ...props}));
const flush = async () => {for (let i = 0; i < 20; i++) await Promise.resolve();};

test('contract types accept older Servers and reject unverified receipt provenance', () => {
  const program = ts.createProgram([fileURLToPath(new URL('./observationContract.types.ts', import.meta.url))], {
    strict: true, noEmit: true, skipLibCheck: true, target: ts.ScriptTarget.ES2022,
    module: ts.ModuleKind.ESNext, moduleResolution: ts.ModuleResolutionKind.Bundler,
  });
  assert.deepEqual(ts.getPreEmitDiagnostics(program).map(item => ts.flattenDiagnosticMessageText(item.messageText, '\n')), []);
});

test('canonical facts precede the external signal, including compact instance rows', () => {
  for (const compact of [false, true]) {
    const html = render(fixture(), {compact});
    assert.ok(html.indexOf('Canonical session facts') < html.indexOf('External activity report'));
    assert.match(html, /Recorded session lifecycle/);
    assert.match(html, /Last receipt received/);
    assert.match(html, /External binding attested by the operator/);
    assert.match(html, /Native process birth checked by the machine/);
    assert.match(html, /Provenance: committed Core receipt/);
    assert.match(html, /Secondary activity signal/);
    assert.match(html, />Working</);
    assert.doesNotMatch(html, />Idle<|<button|<a\b|<form/);
  }
});

test('received terminal stages never infer idle activity or current execution state', () => {
  for (const stage of ['SUCCEEDED', 'FAILED', 'ACCEPTED']) {
    const item = fixture();
    item.canonical_observation.last_received_receipt.stage = stage;
    item.activity_state = 'idle'; item.freshness = 'stale';
    const html = render(item);
    assert.match(html, /Activity unknown/);
    assert.match(html, /Report expired/);
    assert.match(html, /does not establish the current execution state/);
    assert.match(html, /do not establish continuing process liveness, idle activity, presence or available capacity/);
    assert.doesNotMatch(html, />Idle<|>Online<|>Available</);
  }
});

test('missing and unproven receipts have distinct honest states', () => {
  const item = fixture();
  item.canonical_observation.last_received_receipt = null;
  assert.match(render(item), /No receipt received in this snapshot/);
  item.canonical_observation.last_received_receipt = {status: 'unknown', reason: 'receipt_provenance_unavailable'};
  assert.match(render(item), /Receipt unknown: committed Core provenance is unavailable/);
  item.canonical_observation.last_received_receipt = {status: 'verified', provenance: 'external', operation_id: 'UNPROVEN_OPERATION'};
  assert.doesNotMatch(render(item), /UNPROVEN_OPERATION|Provenance: committed Core receipt/);
});

test('canonical and external identifiers remain escaped plaintext without command links', () => {
  const item = fixture();
  item.canonical_session_ref.session_id = '<img src=x onerror=alert(1)>';
  item.canonical_observation.last_received_receipt.action = 'javascript:alert(1)\n<script>bad()</script>';
  item.external_instance_ref = '<a href="https://example.invalid">source</a>';
  const html = render(item);
  assert.match(html, /&lt;img/);
  assert.match(html, /&lt;script&gt;/);
  assert.doesNotMatch(html, /<img|<script|<a\b|<button/);
});

test('null or absent current DTO fields and stale reads never retain canonical refs', () => {
  const item = fixture();
  for (const value of [null, undefined]) {
    assert.doesNotMatch(render({...item, canonical_observation: value}), /canonical-session|received-operation/);
  }
  assert.doesNotMatch(render({...item, canonical_session_ref: null}), /canonical-session|received-operation/);
  const stale = render(item, {currentView: false});
  assert.match(stale, /Canonical correlation must be refreshed/);
  assert.doesNotMatch(stale, /canonical-session|received-operation/);
});

test('refresh replaces a selected correlation with null and authorization loss clears it', async () => {
  let next = {item: fixture()}, clock = 0;
  const reader = new ObservationReader({read: async () => next, refreshAfter: () => 15, now: () => clock,
    setTimeout: () => 1, clearTimeout: () => {}, onChange: () => {}});
  reader.configure({id: 'instance'}); await flush();
  assert.match(render(reader.getState().value.item), /canonical-session/);
  next = {item: {...fixture(), source_revision: 4, canonical_session_ref: null, canonical_observation: null}};
  clock++; reader.refresh(); await flush();
  assert.doesNotMatch(render(reader.getState().value.item), /canonical-session|received-operation/);
  next = {item: fixture()}; reader.refresh(); await flush(); reader.clear();
  assert.equal(reader.getState().value, null);
  assert.equal(reader.getState().status, 'forbidden'); reader.dispose();
});

test('a correlated external occurrence still has no approve, dispatch or canonical navigation authority', async () => {
  const observation = fixture();
  const item = {source_type: 'external_observation', source_id: observation.observed_instance_id,
    agent_id: observation.agent_id, workspace_id: observation.workspace_id,
    kind: 'external_blocked', external_observation: observation, allowed_actions: ['inspect_external_observation']};
  const selected = attentionTarget(item, 'inspect_external_observation');
  for (const action of ['decide_approval', 'respond_native', 'verify_handoff', 'inspect_operation'])
    assert.equal(attentionTarget({...item, allowed_actions: [action]}, action).kind, 'unavailable');
  await assert.rejects(readAttentionReference({externalObservation: async () => ({item: {...observation, generation: 3}})}, selected),
    {code: 'OBSERVATION_SELECTION_CHANGED'});
});

test('agent summary remains an external aggregate without a canonical or capacity aggregate', () => {
  const summary = {status: 'ready', value: {feature_enabled: true, agents: [{agent_id: 'agent', total_instances: 2,
    activity: {working: 1, idle: 0, blocked: 0, unknown: 1}, freshness: {current: 1, stale: 1, unknown: 0, unavailable: 0}}]}};
  const html = renderToStaticMarkup(React.createElement(ExternalAgentActivity, {agentId: 'agent', workspace: 'all', summary}));
  assert.match(html, /External activity/); assert.match(html, /1 working; 1 activity unknown/);
  assert.match(html, /presence and capacity are shown separately/);
  assert.doesNotMatch(html, /Canonical session facts|canonical-session|>Idle</);
});
