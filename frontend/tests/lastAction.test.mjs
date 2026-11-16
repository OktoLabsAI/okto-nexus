import {readFile} from 'node:fs/promises';
import assert from 'node:assert/strict';
import test from 'node:test';
import ts from 'typescript';

const source = await readFile(new URL('../src/graph/lastAction.ts', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, {
  compilerOptions: {module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022},
}).outputText;
const {actionLabel, relativeTime} = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`);

const nowMs = Date.parse('2026-01-01T12:00:00Z');

test('actionLabel("") returns "Activity"', () => {
  assert.equal(actionLabel(''), 'Activity');
});

test('relativeTime: "just now" for a future stamp', () => {
  assert.equal(relativeTime('2026-01-01T12:00:05Z', nowMs), 'just now');
});

test('relativeTime: "just now" for a same-second stamp', () => {
  assert.equal(relativeTime('2026-01-01T12:00:00Z', nowMs), 'just now');
});

test('relativeTime: "1 second ago"', () => {
  assert.equal(relativeTime('2026-01-01T11:59:59Z', nowMs), '1 second ago');
});

test('relativeTime: "59 seconds ago"', () => {
  assert.equal(relativeTime('2026-01-01T11:59:01Z', nowMs), '59 seconds ago');
});

test('relativeTime: "1 minute ago"', () => {
  assert.equal(relativeTime('2026-01-01T11:59:00Z', nowMs), '1 minute ago');
});

test('relativeTime: "2 hours ago"', () => {
  assert.equal(relativeTime('2026-01-01T10:00:00Z', nowMs), '2 hours ago');
});

test('relativeTime: "3 days ago"', () => {
  assert.equal(relativeTime('2025-12-29T12:00:00Z', nowMs), '3 days ago');
});

test('relativeTime: "unknown time" for "garbage"', () => {
  assert.equal(relativeTime('garbage', nowMs), 'unknown time');
});
