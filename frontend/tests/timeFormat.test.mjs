import {readFile} from 'node:fs/promises';
import assert from 'node:assert/strict';
import test from 'node:test';
import ts from 'typescript';

const source = await readFile(new URL('../src/timeFormat.ts', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022}}).outputText;
const {formatTime, isoTitle, msUntil, formatRemaining} = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`);

test('formatTime returns em dash for null, undefined, and empty string', () => {
  assert.equal(formatTime(null), '—');
  assert.equal(formatTime(undefined), '—');
  assert.equal(formatTime(''), '—');
});

test('formatTime returns input unchanged for invalid date', () => {
  assert.equal(formatTime('not a date'), 'not a date');
});

test('isoTitle returns undefined for empty and null, and returns real string as is', () => {
  assert.equal(isoTitle(''), undefined);
  assert.equal(isoTitle(null), undefined);
  assert.equal(isoTitle('2026-01-01T00:00:00Z'), '2026-01-01T00:00:00Z');
});

test('msUntil returns null for empty and invalid input', () => {
  assert.equal(msUntil('', 1000), null);
  assert.equal(msUntil(null, 1000), null);
  assert.equal(msUntil('not a date', 1000), null);
});

test('msUntil returns at - now for a valid ISO string', () => {
  const at = '2026-01-01T00:01:00.000Z';
  const now = Date.parse('2026-01-01T00:00:00.000Z');
  assert.equal(msUntil(at, now), 60000);
});

test('formatRemaining returns expired for 0 and negative values', () => {
  assert.equal(formatRemaining(0), 'expired');
  assert.equal(formatRemaining(-1), 'expired');
  assert.equal(formatRemaining(-60000), 'expired');
});

test('formatRemaining returns 1h 05m left for 65 minutes', () => {
  assert.equal(formatRemaining(65 * 60 * 1000), '1h 05m left');
});

test('formatRemaining returns 5m left for 5 minutes', () => {
  assert.equal(formatRemaining(5 * 60 * 1000), '5m left');
});

test('formatRemaining returns 30s left for 30 seconds and 1s left for 200 ms', () => {
  assert.equal(formatRemaining(30 * 1000), '30s left');
  assert.equal(formatRemaining(200), '1s left');
});
