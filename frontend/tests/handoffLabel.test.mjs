import {readFile} from 'node:fs/promises';
import assert from 'node:assert/strict';
import test from 'node:test';
import ts from 'typescript';

const source = await readFile(new URL('../src/handoffLabel.ts', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, {
  compilerOptions: {module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022},
}).outputText;
const {handoffLabel} = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`);

test('title wins over subject', () => {
  assert.equal(
    handoffLabel({handoff_id: 'h1', payload: {title: '  Main title  ', subject: 'Subject'}}),
    'Main title',
  );
});

test('blank whitespace title falls through to subject', () => {
  assert.equal(
    handoffLabel({handoff_id: 'h1', payload: {title: '   ', subject: '  Subject line  '}}),
    'Subject line',
  );
});

test('array payload falls back to id', () => {
  assert.equal(handoffLabel({handoff_id: 'handoff-123', payload: ['title']}), 'handoff-123');
});

test('null payload falls back to id', () => {
  assert.equal(handoffLabel({handoff_id: 'handoff-456', payload: null}), 'handoff-456');
});

test('returned label is trimmed', () => {
  assert.equal(handoffLabel({handoff_id: 'h1', payload: {title: '  trimmed  '}}), 'trimmed');
  assert.equal(handoffLabel({handoff_id: 'h1', payload: {subject: '\nsubject\t'}}), 'subject');
});
