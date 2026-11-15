import assert from 'node:assert/strict';
import {existsSync, readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import test from 'node:test';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import ts from 'typescript';

// Render the actual presentation, with no browser, service or network.
const require = createRequire(import.meta.url), modules = new Map();
function load(url) {
  const filename = fileURLToPath(url);
  if (modules.has(filename)) return modules.get(filename).exports;
  const module = {exports: {}};
  modules.set(filename, module);
  const compiled = ts.transpileModule(readFileSync(filename, 'utf8'), {fileName: filename, compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX,
  }}).outputText;
  const localRequire = name => {
    if (!name.startsWith('.')) return require(name);
    const path = ['.ts', '.tsx'].map(extension => new URL(name + extension, url)).find(path => existsSync(path));
    assert.ok(path, name);
    return load(path);
  };
  new Function('require', 'module', 'exports', compiled)(localRequire, module, module.exports);
  return module.exports;
}
const {HomeOverview} = load(new URL('../src/views/HomeView.tsx', import.meta.url));
const ready = value => ({value, status: 'ready', loading: false, error: null, key: 'scope'});
const at = '2026-11-15T10:00:00Z';
const fixture = () => ({workspace: 'project',
  graph: ready({nodes: [{agent_id: 'agent-a', presence: 'present', sessions: 2, pending_inbox: 3,
    open_handoffs: 1, last_action: null}], generated_at: at, window_hours: 24}),
  sessions: ready({active_count: 1, total: 25, has_more: true, items: [{
    scope: {executor_id: 'remote-host', session_id: 'session', agent_id: 'agent-a', workspace_id: 'project'},
    harness: 'claude_stream', host: 'build-host', location: 'remote', lifecycle_state: 'READY',
    process_state: 'RUNNING', lease_state: 'ACTIVE', is_open: true, last_interaction_at: at,
  }]}),
  messages: ready({total: 1, items: [{message_id: 'message', from_agent_id: 'agent-a',
    deliveries: [{recipient_agent_id: 'agent-b', status: 'unread'}], subject: '<script>unsafe</script>',
    preview: 'preview', created_at: at, workspace_id: 'project'}]}),
  observations: ready({total_instances: 2, feature_enabled: true, observed_at: at,
    activity: {working: 1, blocked: 0, idle: 0, unknown: 1}, freshness: {current: 1, stale: 1, unknown: 0, unavailable: 0}}),
  attention: {status: 'ready', summary: {filters: {workspace_id: 'project'}, total: 3,
    counts: {action_required: 2, watch: 1, unseen: 3, snoozed: 0}, observed_at: at}},
  onNavigate() {}, onRefresh() {},
});
const render = props => renderToStaticMarkup(React.createElement(HomeOverview, props));

test('presence, lifecycle, external reports and messages remain distinct', () => {
  const html = render(fixture());
  for (const text of ['Connected', '2 connections', 'Claude', 'Remote', 'build-host',
    'process: RUNNING', 'lease: ACTIVE', '1 working; 1 activity unknown (1 expired)', 'agent-b',
    'Showing 1 of 25', '2 need action']) assert.ok(html.includes(text), text);
  assert.ok(html.includes('&lt;script&gt;unsafe&lt;/script&gt;'));
  assert.ok(!html.includes('<script>unsafe'));
  assert.ok(html.includes('Open describes the session, not whether work is running.'));
});

test('failed and unauthorized reads do not masquerade as empty lists', () => {
  for (const status of ['error', 'forbidden', 'unavailable', 'loading']) {
    const props = fixture();
    for (const name of ['graph', 'sessions', 'messages', 'observations']) props[name] = {value: null, status};
    props.attention = {status, summary: null};
    const html = render(props);
    assert.ok(!html.includes('No agents in this scope'));
    assert.ok(!html.includes('No messages in this scope'));
    assert.ok(!html.includes('No active attention items'));
    assert.ok(!html.includes('agent-a'));
    assert.match(html, /Loading|Could not load|Operator access|Unavailable/);
  }
});

test('valid empty snapshots are distinct from unreadable data', () => {
  const props = fixture(); props.graph.value.nodes = []; props.messages.value.items = [];
  props.sessions.value = {items: [], total: 0, active_count: 0, has_more: false};
  props.attention.summary.total = 0; props.attention.summary.counts = {action_required: 0, watch: 0, unseen: 0, snoozed: 0};
  const html = render(props);
  for (const text of ['No agents in this scope', 'No messages in this scope', 'No managed conversations', 'No active attention items']) assert.ok(html.includes(text));
});

test('stale snapshots retain provenance and never claim current external activity', () => {
  const props = fixture();
  for (const name of ['graph', 'sessions', 'messages', 'observations']) props[name].status = 'stale';
  props.attention.status = 'stale';
  const html = render(props);
  assert.ok(html.includes('Out of date'));
  assert.ok(html.includes('snapshot out of date'));
  assert.ok(!html.includes('1 working;'));
  assert.ok(html.includes('last update'));
  assert.ok(html.includes('last summary'));
});

test('workspace transition does not render the previous attention summary', () => {
  const props = fixture(); props.workspace = 'another-project';
  assert.ok(!render(props).includes('2 need action'));
  props.workspace = 'all'; props.attention.summary.filters = {};
  assert.ok(render(props).includes('2 need action'));
});

test('overview navigation opens existing destinations without submitting work', () => {
  const navigated = [], props = fixture(); props.onNavigate = view => navigated.push(view);
  // Expand pure components to exercise the actual buttons, not a parallel mapping.
  function visit(node) {
    if (Array.isArray(node)) return node.forEach(visit);
    if (!React.isValidElement(node)) return;
    if (typeof node.type === 'function') return visit(node.type(node.props));
    if (node.type === 'button' && node.props.onClick !== props.onRefresh) node.props.onClick();
    visit(node.props.children);
  }
  visit(HomeOverview(props));
  assert.deepEqual(new Set(navigated), new Set(['Graph', 'Meta-harness', 'Messages', 'Attention', 'Agents']));
});
