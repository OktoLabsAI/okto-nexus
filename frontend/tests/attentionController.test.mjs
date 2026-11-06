import {readFile} from 'node:fs/promises';
import assert from 'node:assert/strict';
import test from 'node:test';
import ts from 'typescript';

const source = await readFile(new URL('../src/attentionController.ts', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, {compilerOptions: {
  module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022,
}}).outputText;
const {AttentionController} = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`);
const flush = async () => { for (let index = 0; index < 80; index++) await Promise.resolve(); };
const deferred = () => {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return {promise, resolve, reject};
};
const error = (status, code = 'TEST_ERROR') => Object.assign(new Error(code), {status, code});
const item = (id = 'att_item', revision = 0) => ({
  attention_id: id, source_revision: `source:${id}`, kind: 'delivery_parked', category: 'action_required',
  severity: 'warning', priority: 20, agent_id: 'agent:one', workspace_id: 'workspace:one', session_id: null,
  operation_id: null, message_id: 'message:one', result_id: null, executor_id: null,
  source_type: 'message_delivery', source_id: 'delivery:one', first_detected_at: '2030-01-01T00:00:00+00:00',
  last_changed_at: '2030-01-01T00:00:00+00:00', freshness: 'current', summary_code: 'delivery_parked',
  allowed_actions: ['inspect_delivery'], resolution: 'open', active: true, next_change_at: null,
  seen_state: {seen: false, seen_at: null, snoozed: false, snoozed_until: null, revision},
});
const summary = (changes = {}) => ({
  version: 1, filters: {state: 'active', seen: 'all'}, total: 1,
  counts: {action_required: 1, watch: 0, priority: {'10': 0, '20': 1, '30': 0}, unseen: 1, snoozed: 0},
  event_cursor: 7, event_low_watermark: 1, snapshot_revision: 'snapshot:one',
  observed_at: '2030-01-01T00:00:00+00:00', next_refresh_at: '2030-01-01T00:00:15+00:00',
  refresh_after_seconds: 15, ...changes,
});
const page = (changes = {}) => ({...summary(), items: [item()], next_cursor: null, ...changes});
const control = (reason = 'canonical_change', cursor = 8) => ({
  version: 1, event_cursor: cursor, reason,
  clear: ['authorization_lost', 'feature_disabled'].includes(reason),
});

class Clock {
  time = 0;
  sequence = 0;
  timers = new Map();
  set = (callback, delay) => {
    const id = ++this.sequence;
    this.timers.set(id, {at: this.time + delay, callback});
    return id;
  };
  clear = id => this.timers.delete(id);
  async advance(milliseconds) {
    const target = this.time + milliseconds;
    let iterations = 0;
    while (true) {
      const due = [...this.timers.entries()].filter(([, timer]) => timer.at <= target)
        .sort((a, b) => a[1].at - b[1].at || a[0] - b[0])[0];
      if (!due) break;
      assert.ok(++iterations < 1000, 'timer loop must remain bounded');
      this.time = due[1].at;
      this.timers.delete(due[0]);
      due[1].callback();
      await flush();
    }
    this.time = target;
    await flush();
  }
}

function harness() {
  const clock = new Clock(), calls = [], streams = [], states = [];
  const response = {summary: summary(), page: page()};
  const behavior = {
    summary: () => structuredClone(response.summary),
    page: () => structuredClone(response.page),
    seen: (_id, body) => ({version: 1, item: item('att_item', body.preference_revision + 1), observed_at: summary().observed_at}),
    snooze: (_id, body) => ({version: 1, item: item('att_item', body.preference_revision + 1), observed_at: summary().observed_at}),
  };
  let active = 0, peak = 0;
  const invoke = async (kind, args, signal) => {
    calls.push({kind, args: structuredClone(args), signal, at: clock.time});
    active++;
    peak = Math.max(peak, active);
    let finished = false;
    const done = () => { if (!finished) { finished = true; active--; } };
    signal?.addEventListener('abort', done, {once: true});
    try { return await behavior[kind](...args, signal); }
    finally { done(); signal?.removeEventListener('abort', done); }
  };
  const controller = new AttentionController({
    api: {
      attentionSummary: (filters, signal) => invoke('summary', [filters], signal),
      attention: (query, signal) => invoke('page', [query], signal),
      attentionSeen: (id, body, signal) => invoke('seen', [id, body], signal),
      attentionSnooze: (id, body, signal) => invoke('snooze', [id, body], signal),
    },
    now: () => clock.time, setTimeout: clock.set, clearTimeout: clock.clear,
    onChange: state => states.push(structuredClone(state)),
    openStream: options => {
      const stream = {options, closed: false, close() { this.closed = true; }};
      streams.push(stream);
      return stream;
    },
  });
  const start = async (options = {}) => {
    controller.configure({workspace: 'workspace:one', visible: true, enabled: true, ...options});
    await flush();
  };
  return {controller, clock, calls, streams, states, response, behavior, start, peak: () => peak};
}

test('hidden page keeps an independent workspace badge and a bounded timer', async () => {
  const h = harness();
  await h.start({visible: false});
  assert.equal(h.controller.getState().summary.total, 1);
  assert.equal(h.controller.getState().page, null);
  assert.deepEqual(h.calls.map(call => call.kind), ['summary']);
  h.controller.setFilters({kind: 'result_unseen', seen: 'unseen', agent_id: 'other', workspace_id: 'forged'});
  await flush();
  assert.ok(h.calls.every(call => call.kind === 'summary' && JSON.stringify(call.args[0]) === JSON.stringify({workspace_id: 'workspace:one'})));
  await h.clock.advance(15000);
  assert.equal(h.calls.filter(call => call.kind === 'summary').length, 3);
  h.controller.configure({workspace: 'workspace:one', visible: true, enabled: true});
  await flush();
  const query = h.calls.find(call => call.kind === 'page').args[0];
  assert.equal(query.workspace_id, 'workspace:one');
  assert.equal(query.kind, 'result_unseen');
  assert.equal(query.agent_id, 'other');
  h.controller.dispose();
});

test('all-workspaces scope omits the workspace filter and stream parameter', async () => {
  const h = harness();
  await h.start({workspace: 'all'});
  assert.deepEqual(h.calls[0].args[0], {});
  assert.equal(h.calls[1].args[0].workspace_id, undefined);
  assert.equal(h.streams[0].options.workspace, undefined);
  h.controller.dispose();
});

test('continuous invalidation is batched with a one-second maximum wait', async () => {
  const h = harness();
  await h.start();
  const stream = h.streams[0];
  for (let index = 0; index < 10; index++) {
    stream.options.onControl('attention-invalidated', control('canonical_change', index + 8));
    await h.clock.advance(100);
    if (index < 9) assert.equal(h.calls.filter(call => call.kind === 'summary').length, 1);
  }
  assert.equal(h.calls.filter(call => call.kind === 'summary').length, 2);
  assert.equal(h.peak(), 1);
  h.controller.dispose();
});

test('refreshes arriving during a slow request coalesce without overlapping work', async () => {
  const h = harness(), slow = deferred();
  h.behavior.summary = () => slow.promise;
  await h.start();
  for (let index = 0; index < 20; index++) h.controller.refresh();
  await flush();
  assert.equal(h.calls.length, 1);
  h.behavior.summary = () => summary();
  slow.resolve(summary());
  await flush();
  assert.deepEqual(h.calls.map(call => call.kind), ['summary', 'page', 'summary', 'page']);
  assert.equal(h.peak(), 1);
  h.controller.dispose();
});

test('refresh deadline includes request elapsed time and wake rechecks immediately', async () => {
  const h = harness(), slow = deferred();
  h.behavior.summary = () => slow.promise;
  await h.start();
  await h.clock.advance(10000);
  h.behavior.summary = () => summary();
  slow.resolve(summary());
  await flush();
  await h.clock.advance(4999);
  assert.equal(h.calls.filter(call => call.kind === 'summary').length, 1);
  await h.clock.advance(1);
  assert.equal(h.calls.filter(call => call.kind === 'summary').length, 2);
  h.controller.wake();
  await flush();
  assert.equal(h.calls.filter(call => call.kind === 'summary').length, 3);
  h.controller.dispose();
});

test('workspace transition aborts old work and ignores its late unauthorized response', async () => {
  const h = harness(), old = deferred();
  h.behavior.summary = () => old.promise;
  await h.start();
  const oldCall = h.calls[0];
  h.behavior.summary = () => summary({total: 9});
  h.controller.configure({workspace: 'workspace:two', visible: true, enabled: true});
  await flush();
  assert.equal(oldCall.signal.aborted, true);
  assert.equal(h.streams[0].closed, true);
  old.reject(error(401, 'AUTH_FAILED'));
  h.streams[0].options.onControl('attention-reset', control('authorization_lost'));
  await flush();
  assert.equal(h.controller.getState().status, 'ready');
  assert.equal(h.controller.getState().summary.total, 9);
  assert.equal(h.controller.getFilters().workspace_id, 'workspace:two');
  assert.equal(h.peak(), 1);
  h.controller.dispose();
});

test('filter changes cancel an old page without adopting its late content', async () => {
  const h = harness(), old = deferred();
  h.behavior.page = () => old.promise;
  await h.start();
  const oldPage = h.calls.find(call => call.kind === 'page');
  h.behavior.page = () => page({items: [item('new-filter')]});
  h.controller.setFilters({state: 'all', seen: 'snoozed'});
  await flush();
  old.resolve(page({items: [item('old-filter')]}));
  await flush();
  assert.equal(oldPage.signal.aborted, true);
  assert.deepEqual(h.controller.getState().page.items.map(row => row.attention_id), ['new-filter']);
  assert.ok(h.calls.filter(call => call.kind === 'summary').every(call => call.args[0].seen === undefined));
  h.controller.dispose();
});

test('pagination appends only one stable page and respects an exhausted cursor', async () => {
  const h = harness();
  h.response.page = page({next_cursor: 'opaque:cursor/one'});
  await h.start();
  h.behavior.page = query => {
    assert.equal(query.cursor, 'opaque:cursor/one');
    return page({items: [item('att_second')], next_cursor: null});
  };
  h.controller.loadMore(); h.controller.loadMore();
  await flush();
  assert.deepEqual(h.controller.getState().page.items.map(row => row.attention_id), ['att_item', 'att_second']);
  const count = h.calls.length;
  h.controller.loadMore();
  await flush();
  assert.equal(h.calls.length, count);
  h.controller.dispose();
});

test('pagination409 discards every previous page and obtains a fresh snapshot', async () => {
  const h = harness();
  h.response.page = page({next_cursor: 'old-cursor', items: [item('old-page')]});
  await h.start();
  h.behavior.page = query => {
    if (query.cursor) throw error(409, 'CONFLICT');
    return page({snapshot_revision: 'snapshot:two', items: [item('fresh-page')]});
  };
  h.controller.loadMore();
  await flush();
  assert.ok(h.states.some(state => state.notice && state.page === null));
  assert.deepEqual(h.controller.getState().page.items.map(row => row.attention_id), ['fresh-page']);
  assert.equal(h.controller.getState().page.snapshot_revision, 'snapshot:two');
  assert.match(h.controller.getState().notice, /changed/);
  h.controller.dispose();
});

test('inconsistent pagination never merges changed revisions or duplicate episodes', async () => {
  for (const invalid of [page({snapshot_revision: 'changed', items: [item('second')]}), page()]) {
    const h = harness();
    h.response.page = page({next_cursor: 'cursor'});
    await h.start();
    h.behavior.page = query => query.cursor ? invalid : page({items: [item('fresh')]});
    h.controller.loadMore();
    await flush();
    assert.deepEqual(h.controller.getState().page.items.map(row => row.attention_id), ['fresh']);
    h.controller.dispose();
  }
});

test('network failures retain last authorized page and badge without false zeros', async () => {
  const h = harness();
  await h.start();
  const previous = h.controller.getState();
  h.behavior.summary = h.behavior.page = () => { throw new Error('Connection unavailable'); };
  h.controller.refresh();
  await flush();
  assert.equal(h.controller.getState().status, 'stale');
  assert.deepEqual(h.controller.getState().page, previous.page);
  assert.deepEqual(h.controller.getState().summary, previous.summary);
  assert.match(h.controller.getState().error, /Connection/);
  h.behavior.summary = () => summary(); h.behavior.page = () => page();
  await h.clock.advance(5000);
  assert.equal(h.controller.getState().status, 'ready');
  h.controller.dispose();
});

test('initial network failure remains unknown and a timed-out request cannot block retries', async () => {
  const h = harness(), hung = deferred();
  h.behavior.summary = () => hung.promise;
  await h.start({visible: false});
  await h.clock.advance(15000);
  assert.equal(h.calls[0].signal.aborted, true);
  assert.equal(h.controller.getState().summary, null);
  assert.equal(h.controller.getState().status, 'error');
  h.behavior.summary = () => summary();
  await h.clock.advance(5000);
  assert.equal(h.controller.getState().status, 'ready');
  hung.resolve(summary({total: 0}));
  await flush();
  assert.equal(h.controller.getState().summary.total, 1);
  h.controller.dispose();
});

test('seen and snooze send captured CAS once, with no optimistic canonical change', async () => {
  const h = harness(), save = deferred();
  h.response.page = page({items: [item('att_reference:opaque', 4)]});
  await h.start();
  const original = h.controller.getState().page.items[0];
  h.behavior.seen = () => save.promise;
  const first = h.controller.markSeen(original, true);
  assert.strictEqual(h.controller.markSeen(original, false), first);
  await flush();
  assert.deepEqual(h.controller.getState().pendingIds, [original.attention_id]);
  assert.deepEqual(h.controller.getState().page.items[0], original);
  assert.deepEqual(h.calls.find(call => call.kind === 'seen').args, [original.attention_id,
    {source_revision: original.source_revision, preference_revision: 4, seen: true}]);
  h.response.page = page({items: [item(original.attention_id, 5)]});
  save.resolve({version: 1, item: item(original.attention_id, 5), observed_at: summary().observed_at});
  await first; await flush();
  assert.deepEqual(h.controller.getState().pendingIds, []);
  await h.controller.snooze(h.controller.getState().page.items[0], null); await flush();
  assert.deepEqual(h.calls.find(call => call.kind === 'snooze').args[1],
    {source_revision: original.source_revision, preference_revision: 5, until: null});
  h.controller.dispose();
});

test('lost mutation response reconciles with reads and never resubmits the preference', async () => {
  const h = harness();
  await h.start();
  h.behavior.seen = () => {
    h.response.page = page({items: [item('att_item', 1)]});
    throw new Error('Response lost');
  };
  await h.controller.markSeen(h.controller.getState().page.items[0], true); await flush();
  assert.equal(h.calls.filter(call => call.kind === 'seen').length, 1);
  assert.equal(h.controller.getState().page.items[0].seen_state.revision, 1);
  h.controller.dispose();
});

test('mutation409 refreshes CAS and a stale click is never sent', async () => {
  const h = harness();
  await h.start();
  const old = h.controller.getState().page.items[0];
  h.behavior.seen = () => { h.response.page = page({items: [item('att_item', 2)]}); throw error(409, 'CONFLICT'); };
  await h.controller.markSeen(old, true); await flush();
  assert.equal(h.controller.getState().page.items[0].seen_state.revision, 2);
  await h.controller.markSeen(old, true); await flush();
  assert.equal(h.calls.filter(call => call.kind === 'seen').length, 1);
  h.controller.dispose();
});

test('closed SSE reauthorizes through HTTP and clears on401 without reconnecting', async () => {
  const h = harness();
  await h.start();
  h.behavior.summary = () => { throw error(401, 'AUTH_FAILED'); };
  h.streams[0].options.onError();
  await flush();
  assert.equal(h.controller.getState().status, 'forbidden');
  assert.equal(h.controller.getState().summary, null);
  assert.equal(h.controller.getState().page, null);
  const count = h.calls.length;
  await h.clock.advance(30000);
  assert.equal(h.calls.length, count);
  assert.equal(h.streams.length, 1);
  h.controller.dispose();
});

test('stream loss with available API retains data and reconnects with current cursor', async () => {
  const h = harness();
  await h.start();
  h.streams[0].options.onControl('attention-reset', control('source_unavailable'));
  await flush();
  assert.equal(h.controller.getState().summary.total, 1);
  assert.equal(h.controller.getState().streamStatus, 'reconnecting');
  await h.clock.advance(1000);
  assert.equal(h.streams.length, 2);
  assert.equal(h.streams[1].options.cursor, 8);
  h.streams[1].options.onOpen();
  assert.equal(h.controller.getState().streamStatus, 'live');
  h.controller.dispose();
});

for (const source of ['source_unavailable', 'transport_error']) {
  test(`${source} immediately marks a pending preference snapshot stale without replay`, async () => {
    const h = harness(), save = deferred();
    h.response.page = page({items: [item('first', 4), item('second', 2)]});
    await h.start();
    const before = h.controller.getState();
    h.behavior.seen = () => save.promise;
    const pending = h.controller.markSeen(before.page.items[0], true);
    await flush();
    const write = h.calls.find(call => call.kind === 'seen');
    if (source === 'source_unavailable') {
      h.streams[0].options.onControl('attention-reset', control(source));
    } else h.streams[0].options.onError();
    const stale = h.controller.getState();
    assert.equal(stale.status, 'stale');
    assert.equal(stale.streamStatus, 'reconnecting');
    assert.deepEqual(stale.page, before.page);
    assert.deepEqual(stale.summary, before.summary);
    assert.deepEqual(stale.pendingIds, ['first']);
    assert.equal(write.signal.aborted, false);
    await flush();
    assert.deepEqual(h.calls.map(call => call.kind), ['summary', 'page', 'seen']);
    h.response.page = page({items: [item('first', 5), item('second', 2)]});
    save.resolve({version: 1, item: item('first', 5), observed_at: summary().observed_at});
    await pending; await flush();
    assert.deepEqual(h.calls.map(call => call.kind), ['summary', 'page', 'seen', 'summary', 'page']);
    assert.equal(h.controller.getState().status, 'ready');
    assert.equal(h.controller.getState().page.items[0].seen_state.revision, 5);
    assert.deepEqual(h.controller.getState().pendingIds, []);
    assert.equal(h.peak(), 1);
    h.controller.dispose();
  });
}

test('reset and retention gaps request snapshots without exposing historical notifications', async () => {
  const h = harness();
  await h.start();
  for (const reason of ['snapshot_required', 'retention_gap']) {
    h.streams[0].options.onControl('attention-reset', {...control(reason), body: 'never copied', title: 'never copied'});
    await h.clock.advance(250);
    assert.equal(h.controller.getState().status, 'ready');
    assert.equal(h.controller.getState().notice, null);
    assert.ok(!JSON.stringify(h.controller.getState()).includes('never copied'));
  }
  h.controller.dispose();
});

test('authorization loss,403 and featureoff clear authorized data and timers', async () => {
  for (const [reason, expected] of [['authorization_lost', 'forbidden'], ['feature_disabled', 'disabled']]) {
    const h = harness(); await h.start();
    h.streams[0].options.onControl('attention-reset', control(reason));
    assert.equal(h.controller.getState().status, expected);
    assert.equal(h.controller.getState().page, null);
    assert.equal(h.clock.timers.size, 0);
    h.controller.dispose();
  }
  for (const failure of [error(403, 'PERMISSION_DENIED'), error(409, 'FEATURE_DISABLED')]) {
    const h = harness(); await h.start();
    h.behavior.summary = () => { throw failure; };
    h.controller.refresh(); await flush();
    assert.equal(h.controller.getState().status, failure.status === 403 ? 'forbidden' : 'disabled');
    assert.equal(h.controller.getState().summary, null);
    h.controller.dispose();
  }
});

test('clear, disable and unmount ignore late successful requests and resolve pending actions', async () => {
  for (const action of ['clear', 'dispose', 'disable']) {
    const h = harness(), save = deferred();
    await h.start();
    h.behavior.seen = () => save.promise;
    const pending = h.controller.markSeen(h.controller.getState().page.items[0], true);
    await flush();
    if (action === 'disable') h.controller.configure({workspace: 'workspace:one', visible: true, enabled: false});
    else h.controller[action]();
    await pending;
    const count = h.calls.length;
    save.resolve({version: 1, item: item('late'), observed_at: summary().observed_at});
    await flush(); await h.clock.advance(60000);
    assert.equal(h.controller.getState().page, null);
    assert.equal(h.controller.getState().summary, null);
    assert.deepEqual(h.controller.getState().pendingIds, []);
    assert.equal(h.calls.length, count);
    assert.ok(h.streams.every(stream => stream.closed));
    h.controller.dispose();
  }
});

test('repeated conflict is bounded and malformed stream controls cannot authorize or clear data', async () => {
  const h = harness(); await h.start();
  h.streams[0].options.onControl('attention-reset', {version: 1, reason: 'canonical_change', clear: true, event_cursor: 9});
  await flush();
  assert.equal(h.controller.getState().summary.total, 1);
  assert.notEqual(h.controller.getState().status, 'forbidden');
  h.behavior.page = () => { throw error(409, 'CONFLICT'); };
  h.controller.refresh(); await flush();
  const count = h.calls.length;
  await flush();
  assert.equal(h.calls.length, count);
  assert.equal(h.controller.getState().page, null);
  h.controller.dispose();
});
