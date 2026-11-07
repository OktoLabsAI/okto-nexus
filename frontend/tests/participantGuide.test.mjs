import assert from 'node:assert/strict';
import {existsSync, readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import test from 'node:test';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import ts from 'typescript';

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
    const candidate = ['.ts', '.tsx'].map(extension => new URL(name + extension, url)).find(path => existsSync(path));
    assert.ok(candidate, `Local module exists: ${name}`);
    return load(candidate);
  };
  new Function('require', 'module', 'exports', compiled)(localRequire, module, module.exports);
  return module.exports;
}
const {ParticipantGuide} = load(new URL('../src/components/ParticipantGuide.tsx', import.meta.url));
const render = props => renderToStaticMarkup(React.createElement(ParticipantGuide,
  {initialOrigin: 'https://nexus.example:9443', ...props}));

test('an existing identity opens guidance without key input, network or implicit setup', () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = () => {throw new Error('Guidance must not make a request');};
  try {
    const html = render({agentId: 'existing-agent', workspaceId: 'workspace-1'});
    assert.match(html, /readonly=""[^>]*value="existing-agent"/);
    assert.ok(html.includes('value="workspace-1"'));
    assert.ok(html.includes('value="https://nexus.example:9443"'));
    assert.ok(html.includes('copying them applies no changes'));
    assert.ok(!html.includes('type="password"') && !html.includes('Authorization: Bearer'));
    assert.ok(html.includes('Copy public command'));
    assert.ok(!html.includes('type="checkbox"'));
  } finally {globalThis.fetch = originalFetch;}
});

test('onboarding requires explicit identity and workspace and labels unknown clients honestly', () => {
  const html = render({});
  assert.ok(html.includes('Existing agent ID') && html.includes('Existing workspace ID'));
  assert.ok(!html.includes('readonly=""'));
  assert.ok(html.includes('Claude Code') && html.includes('Codex'));
  assert.ok(html.includes('Other client — manual guidance'));
  assert.ok(html.includes('Missing identities require a separate explicit operator decision'));
});

test('the guide separates one-shot delivery and proof levels from public commands', () => {
  const html = render({agentId: 'existing-agent'});
  for (const expected of ['one-shot key delivery stays separate', 'hidden CLI prompt',
    'Configuration, credential delivery to a client, MCP negotiation and completed work are separate proofs',
    'process exit does not prove participation or completed work']) {
    assert.ok(html.includes(expected), expected);
  }
  assert.ok(!html.includes('mcp-copy-') && !html.includes('export OKTO_NEXUS_API_KEY'));
});

test('loopback has contextual guidance without blocking public commands', () => {
  const html = render({initialOrigin: 'http://127.0.0.1:8202', agentId: 'existing-agent', workspaceId: 'workspace-1'});
  assert.ok(html.includes('Loopback refers to the client computer'));
  assert.ok(html.includes('HTTP sends plaintext on this host'));
  assert.ok(!html.includes('type="checkbox"') && html.includes('Copy public command'));
});

test('untrusted identity text stays escaped', () => {
  const html = render({agentId: '<script>alert(1)</script>'});
  assert.ok(!html.includes('<script>'));
  assert.ok(html.includes('&lt;script&gt;alert(1)&lt;/script&gt;'));
});
