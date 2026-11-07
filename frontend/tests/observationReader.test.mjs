import {readFile} from 'node:fs/promises';
import assert from 'node:assert/strict';
import test from 'node:test';
import ts from 'typescript';

const source = await readFile(new URL('../src/observationReader.ts', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022}}).outputText;
const {ObservationReader} = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`);
const flush = async () => {for (let i = 0; i < 20; i++) await Promise.resolve();};
const deferred = () => {let resolve, reject; const promise = new Promise((yes, no) => {resolve = yes; reject = no;}); return {promise, resolve, reject};};
const failure = (status, code = 'ERROR') => Object.assign(new Error('secret detail must not appear'), {status, code});
function harness() {
  const calls = [], changes = [], timers = new Map();
  let time = 0, sequence = 0;
  const behavior = {read: query => ({scope: query, refresh_after_seconds: 15, feature_enabled: true})};
  const reader = new ObservationReader({
    read: (query, signal) => {calls.push({query, signal, at: time}); return Promise.resolve().then(() => behavior.read(query, signal));},
    refreshAfter: value => value.refresh_after_seconds, now: () => time,
    setTimeout: (callback, milliseconds) => {const id = ++sequence; timers.set(id, {at: time + milliseconds, callback}); return id;},
    clearTimeout: id => timers.delete(id), onChange: state => changes.push(state),
  });
  const advance = async ms => {
    const until = time + ms;
    for (let iteration = 0; ; iteration++) {
      assert.ok(iteration < 100, 'refresh loop stays bounded');
      const due = [...timers.entries()].filter(([, row]) => row.at <= until).sort((a, b) => a[1].at - b[1].at)[0];
      if (!due) break;
      time = due[1].at; timers.delete(due[0]); due[1].callback(); await flush();
    }
    time = until; await flush();
  };
  return {reader, calls, changes, behavior, advance, timers};
}

test('one summary request serves a scope and bursts coalesce without parallel reads', async () => {
  const h = harness(), pending = deferred(); h.behavior.read = () => pending.promise;
  h.reader.configure({workspace_id: 'one'}); await flush();
  for (let i = 0; i < 10; i++) h.reader.refresh();
  assert.equal(h.calls.length, 1);
  h.behavior.read = query => ({scope: query, refresh_after_seconds: 15});
  pending.resolve({refresh_after_seconds: 15}); await flush();
  assert.equal(h.calls.length, 2); assert.equal(h.reader.getState().status, 'ready');
  h.reader.dispose();
});

test('changing workspace or page clears the prior result before loading', async () => {
  const h = harness(); h.reader.configure({workspace_id: 'one'}); await flush();
  const pending = deferred(); h.behavior.read = () => pending.promise;
  h.reader.configure({workspace_id: 'two', after: 'page2'});
  assert.equal(h.reader.getState().value, null); assert.equal(h.reader.getState().status, 'loading');
  pending.resolve({scope: 'new', refresh_after_seconds: 15}); await flush();
  assert.equal(h.reader.getState().value.scope, 'new'); h.reader.dispose();
});

test('late responses and authorization errors from an old scope do not change the new scope', async () => {
  for (const lateError of [false, true]) {
    const h = harness(), pending = deferred(); h.behavior.read = query => query.workspace === 'old' ? pending.promise : {scope: 'new', refresh_after_seconds: 15};
    h.reader.configure({workspace: 'old'}); await flush(); h.reader.configure({workspace: 'new'}); await flush();
    assert.equal(h.calls[0].signal.aborted, true);
    if (lateError) pending.reject(failure(403)); else pending.resolve({scope: 'old', refresh_after_seconds: 15});
    await flush(); assert.equal(h.reader.getState().value.scope, 'new'); assert.equal(h.reader.getState().status, 'ready'); h.reader.dispose();
  }
});

test('subsecond TTL marks the snapshot stale before the refresh response arrives', async () => {
  const h = harness(); h.behavior.read = () => ({refresh_after_seconds: 0.25});
  h.reader.configure({}); await flush(); const pending = deferred(); h.behavior.read = () => pending.promise;
  await h.advance(249); assert.equal(h.reader.getState().status, 'ready');
  await h.advance(1); assert.equal(h.reader.getState().status, 'stale'); assert.equal(h.reader.getState().loading, true);
  h.reader.dispose(); pending.resolve({refresh_after_seconds: 15}); await flush();
});

test('network transit consumes freshness instead of extending the Server TTL', async () => {
  const h = harness(), pending = deferred(); h.behavior.read = () => pending.promise;
  h.reader.configure({}); await flush(); await h.advance(2000);
  pending.resolve({refresh_after_seconds: 1}); await flush();
  assert.equal(h.reader.getState().status, 'stale');
  assert.equal(h.calls.length, 1); h.reader.dispose();
});

test('transient failure retains only explicitly stale data and uses a bounded retry', async () => {
  const h = harness(); h.reader.configure({}); await flush(); h.behavior.read = () => {throw failure(503);};
  h.reader.refresh(); await flush();
  assert.equal(h.reader.getState().status, 'stale'); assert.ok(h.reader.getState().value);
  assert.doesNotMatch(h.reader.getState().error, /secret/);
  await h.advance(14999); assert.equal(h.calls.length, 2);
  await h.advance(1); assert.equal(h.calls.length, 3); h.reader.dispose();
});

test('a hung refresh times out, aborts its request and never keeps old data current', async () => {
  const h = harness(); h.reader.configure({}); await flush();
  const pending = deferred(); h.behavior.read = () => pending.promise;
  h.reader.refresh(); await flush(); assert.equal(h.reader.getState().status, 'stale');
  await h.advance(15000); assert.equal(h.calls[1].signal.aborted, true);
  assert.equal(h.reader.getState().loading, false); assert.equal(h.reader.getState().status, 'stale');
  h.reader.dispose(); pending.resolve({refresh_after_seconds: 15}); await flush();
});

test('current authorization loss clears protected data and stops automatic polling', async () => {
  for (const status of [401, 403]) {
    const h = harness(); h.reader.configure({}); await flush(); h.behavior.read = () => {throw failure(status);};
    h.reader.refresh(); await flush(); assert.equal(h.reader.getState().value, null);
    assert.equal(h.reader.getState().status, 'forbidden'); assert.equal(h.reader.getState().loading, false);
    await h.advance(60000); assert.equal(h.calls.length, 2); h.reader.dispose();
  }
});

test('missing endpoint and changed generation clear the selected report without fallback', async () => {
  for (const error of [failure(404), failure(409, 'OBSERVATION_SELECTION_CHANGED')]) {
    const h = harness(); h.reader.configure({instance: 'old'}); await flush(); h.behavior.read = () => {throw error;};
    h.reader.refresh(); await flush(); assert.equal(h.reader.getState().value, null);
    assert.equal(h.reader.getState().status, 'unavailable');
    await h.advance(60000); assert.equal(h.calls.length, 2); h.reader.dispose();
  }
});

test('disabled publishing keeps explicitly unavailable history consultable and can refresh', async () => {
  const h = harness(); h.behavior.read = () => ({feature_enabled: false, refresh_after_seconds: 15, activity: 'unknown'});
  h.reader.configure({}); await flush(); assert.equal(h.reader.getState().value.feature_enabled, false);
  await h.advance(15000); assert.equal(h.calls.length, 2); h.reader.dispose();
});

test('collapsed panels and disposed readers cancel requests and never publish late results', async () => {
  const h = harness(), pending = deferred(); h.behavior.read = () => pending.promise;
  h.reader.configure({agent: 'one'}); await flush(); h.reader.configure(null);
  assert.equal(h.calls[0].signal.aborted, true); assert.equal(h.reader.getState().value, null);
  const before = h.changes.length; h.reader.dispose(); pending.resolve({refresh_after_seconds: 15}); await flush();
  await h.advance(60000); assert.equal(h.changes.length, before); assert.equal(h.calls.length, 1);
});

test('zero and invalid refresh durations remain stale and do not cause a tight loop', async () => {
  for (const seconds of [0, -1, NaN, Infinity]) {
    const h = harness(); h.behavior.read = () => ({refresh_after_seconds: seconds});
    h.reader.configure({}); await flush(); assert.equal(h.reader.getState().status, 'stale');
    await h.advance(999); assert.equal(h.calls.length, 1); h.reader.dispose();
  }
});
