import {readFile} from 'node:fs/promises';
import assert from 'node:assert/strict';
import test from 'node:test';
import ts from 'typescript';

const source = await readFile(new URL('../src/operatorUnread.ts', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022}}).outputText;
const {newItems, isNewForOperator, toastText} = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`);

const delivery = (recipient, status, created) => ({recipient_agent_id: recipient, status, created_at: created});
const item = (id, subject = null, preview = '') => ({message_id: id, workspace_id: 'w', from_agent_id: 'lead', subject, preview, created_at: '2030-01-01T00:00:01+00:00'});

test('newItems skips messages that the toast logic already reported', () => {
  const found = newItems([item('a'), item('b'), item('c')], new Set(['b']));
  assert.deepEqual(found.map(entry => entry.message_id), ['a', 'c']);
});

test('isNewForOperator needs an unread delivery to the operator', () => {
  assert.equal(isNewForOperator([delivery('operator', 'unread', '2030-01-01T00:00:05+00:00')], null), true);
  assert.equal(isNewForOperator([delivery('operator', 'read', '2030-01-01T00:00:05+00:00')], null), false);
  assert.equal(isNewForOperator([delivery('worker', 'unread', '2030-01-01T00:00:05+00:00')], null), false);
});

test('isNewForOperator ignores deliveries at or before the seen marker', () => {
  const marker = '2030-01-01T00:00:05+00:00';
  assert.equal(isNewForOperator([delivery('operator', 'unread', marker)], marker), false);
  assert.equal(isNewForOperator([delivery('operator', 'unread', '2030-01-01T00:00:06+00:00')], marker), true);
});

test('toastText prefers the subject, then the preview', () => {
  assert.equal(toastText(item('a', 'Milestone', 'body')), 'Milestone');
  assert.equal(toastText(item('a', null, 'body')), 'body');
  assert.equal(toastText(item('a')), '(no subject)');
});
