import {readFile} from 'node:fs/promises';
import assert from 'node:assert/strict';
import test from 'node:test';
import ts from 'typescript';

globalThis.location = {hostname: '127.0.0.1', port: '8202'};
const source = await readFile(new URL('../src/api.ts', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022}}).outputText;
const {mcpSnippet} = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`);
const KEY = 'nxs_example';

test('no format puts the key in the URL', () => {
  for (const format of ['claude-cli', 'codex', 'vscode', 'claude', 'cursor', 'windsurf', 'other']) {
    assert.ok(!mcpSnippet(format, KEY).includes('api_key='), format);
  }
});

test('the claude command sends the key in a Bearer header', () => {
  assert.equal(mcpSnippet('claude-cli', KEY),
    'claude mcp add -t http okto-nexus "http://127.0.0.1:8202/mcp" --header "Authorization: Bearer nxs_example"');
});

test('the codex command reads the key from OKTO_NEXUS_API_KEY', () => {
  const [exportLine, addLine] = mcpSnippet('codex', KEY).split('\n');
  assert.equal(exportLine, 'export OKTO_NEXUS_API_KEY="nxs_example"');
  assert.equal(addLine, 'codex mcp add okto-nexus --url "http://127.0.0.1:8202/mcp" --bearer-token-env-var OKTO_NEXUS_API_KEY');
});

test('JSON formats carry the Bearer header next to the URL', () => {
  const vscode = JSON.parse(mcpSnippet('vscode', KEY));
  assert.deepEqual(vscode.servers['okto-nexus'].headers, {Authorization: 'Bearer nxs_example'});
  const claude = JSON.parse(mcpSnippet('claude', KEY));
  assert.deepEqual(claude.mcpServers['okto-nexus'], {url: 'http://127.0.0.1:8202/mcp', headers: {Authorization: 'Bearer nxs_example'}});
});
