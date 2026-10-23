import {readFile} from 'node:fs/promises';
import assert from 'node:assert/strict';
import test from 'node:test';
import ts from 'typescript';

const source = await readFile(new URL('../src/sessionRestarts.ts', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022}}).outputText;
const {restartMarkers, placeMarkers} = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`);

const session = (id, agent, last, open = false, reason) => ({
  scope: {session_id: id, agent_id: agent, workspace_id: 'w'}, is_open: open, last_interaction_at: last,
  ...(reason ? {containment_reason: reason} : {}),
});

test('an ended session with a later session of the same agent is a restart', () => {
  const markers = restartMarkers([
    session('new', 'claude', '2030-01-01T00:10:00Z', true),
    session('old', 'claude', '2030-01-01T00:05:00Z', false, 'contained'),
  ]);
  assert.deepEqual(markers, [{id: 'old', agentId: 'claude', after: '2030-01-01T00:05:00Z', reason: 'contained'}]);
});

test('the last session, an open session and another agent are not restarts', () => {
  assert.deepEqual(restartMarkers([session('only', 'claude', '2030-01-01T00:05:00Z')]), []);
  assert.deepEqual(restartMarkers([
    session('open-old', 'claude', '2030-01-01T00:05:00Z', true),
    session('new', 'claude', '2030-01-01T00:10:00Z', true),
  ]), []);
  assert.deepEqual(restartMarkers([
    session('a', 'claude', '2030-01-01T00:05:00Z'),
    session('b', 'codex', '2030-01-01T00:10:00Z'),
  ]), []);
});

test('the divider goes above the first operator message after the ended session', () => {
  const entries = [
    {timestamp: '2030-01-01T00:05:00Z', direction: 'outgoing', recipients: ['claude']},
    {timestamp: '2030-01-01T00:06:00Z', direction: 'incoming', recipients: ['operator']},
    {timestamp: '2030-01-01T00:09:00Z', direction: 'outgoing', recipients: ['codex']},
    {timestamp: '2030-01-01T00:10:00Z', direction: 'outgoing', recipients: ['claude']},
  ];
  const marker = {id: 'old', agentId: 'claude', after: '2030-01-01T00:05:00Z', reason: null};
  const placed = placeMarkers(entries, [marker]);
  assert.deepEqual([...placed.keys()], [3]);
  assert.deepEqual(placed.get(3), [marker]);
  assert.equal(placeMarkers(entries.slice(0, 3), [marker]).size, 0);
});
