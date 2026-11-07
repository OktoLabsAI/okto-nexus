import {readFile} from 'node:fs/promises';
import assert from 'node:assert/strict';
import test from 'node:test';
import ts from 'typescript';

const source = await readFile(new URL('../src/observationPresentation.ts', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022}}).outputText;
const {observationCountText, observationStatus, observationRefreshSeconds} =
  await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`);
const counts = {total_instances: 9, activity: {working: 2, idle: 1, blocked: 1, unknown: 5},
  freshness: {current: 5, stale: 2, unknown: 1, unavailable: 1}};

test('complete aggregate retains mixed instances and unavailable evidence separately', () => {
  assert.equal(observationCountText(counts, true), '2 working; 1 idle; 1 awaiting input; 5 activity unknown (2 expired; 1 unavailable; 1 without a report)');
  assert.equal(observationCountText(counts, false), '9 external instances · snapshot out of date');
  assert.deepEqual(counts.activity, {working: 2, idle: 1, blocked: 1, unknown: 5});
});

test('only current observations display reported activity; stale never becomes idle', () => {
  for (const freshness of ['stale', 'unknown', 'unavailable']) {
    assert.equal(observationStatus({activity_state: 'idle', freshness}, true).activity, 'Activity unknown');
  }
  assert.equal(observationStatus({activity_state: 'blocked', freshness: 'current'}, true).activity, 'Awaiting input');
  assert.deepEqual(observationStatus({activity_state: 'working', freshness: 'current'}, false),
    {activity: 'Activity unknown', freshness: 'Snapshot out of date'});
});

test('next refresh uses the Server clock and the earliest current report TTL', () => {
  const value = {observed_at: '2030-01-01T10:00:00Z', items: [
    {freshness: 'current', last_report: {valid_until: '2030-01-01T07:00:00.250-03:00'}},
    {freshness: 'current', last_report: {valid_until: '2030-01-01T10:00:10Z'}},
    {freshness: 'stale', last_report: {valid_until: '2020-01-01T00:00:00Z'}},
  ]};
  assert.equal(observationRefreshSeconds(value), 0.25);
  assert.equal(observationRefreshSeconds({...value, items: []}), 15);
  assert.equal(observationRefreshSeconds({...value, refresh_after_seconds: 0.1}), 0.1);
  assert.equal(observationRefreshSeconds({observed_at: value.observed_at, item: value.items[1], refresh_after_seconds: 30}), 10);
});

test('expired, absent or invalid freshness deadlines cannot assert current activity', () => {
  const value = {observed_at: '2030-01-01T10:00:00Z', refresh_after_seconds: 15};
  for (const valid_until of [null, '', 'invalid', '2030-01-01T09:00:00Z'])
    assert.equal(observationRefreshSeconds({...value, item: {freshness: 'current', last_report: {valid_until}}}), 0);
  for (const refresh_after_seconds of [-1, NaN, Infinity])
    assert.equal(observationRefreshSeconds({...value, refresh_after_seconds}), 0);
  assert.equal(observationRefreshSeconds({...value, observed_at: 'invalid'}), 0);
});
