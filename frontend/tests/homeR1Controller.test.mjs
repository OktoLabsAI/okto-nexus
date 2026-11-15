import assert from 'node:assert/strict';
import test from 'node:test';
import { moduleURL, Clock, deferred, flush, overview, section, page } from './homeR1Support.mjs';
const { HomeController, homeInvalidatedSections, homeContextKey } = await import(await moduleURL('homeController.ts'));
const { homeExternalLabel } = await import(await moduleURL('homePresentation.ts'));
const error = status => Object.assign(new Error('fixture'), { status, code: `HTTP_${status}` });
function harness() {
  const clock = new Clock(), calls = [], changes = [];
  let active = 0, peak = 0;
  const behavior = { overview: () => overview(), work: () => page([{ id: 'work2' }]), results: () => page([]), activity: () => page([]),
    agents: () => page([]), external: () => page([]), attention: () => ({}) };
  const api = Object.fromEntries(Object.keys(behavior).map(kind => [kind, async (query, signal) => {
    calls.push({ kind, query, signal, at: clock.now }); active++; peak = Math.max(peak, active);
    try { return await behavior[kind](query, signal); } finally { active--; }
  }]));
  const controller = new HomeController({ api, now: () => clock.now, setTimeout: clock.set, clearTimeout: clock.clear,
    onChange: value => changes.push(value) });
  const configure = (patch = {}) => controller.configure({ workspace: 'ws', identityKey: 'operator1', origin: 'https://one', visible: true, enabled: true, ...patch });
  return { controller, configure, clock, calls, changes, behavior, peak: () => peak };
}
test('bursts coalesce while pending and never exceed one read/second', async () => {
  const h = harness(), pending = deferred(); h.behavior.overview = () => pending.promise;
  h.configure(); await h.clock.advance();
  for (let i = 0; i < 100; i++) h.controller.invalidate({ type: 'handoff.changed', event_id: i });
  await h.clock.advance(1000); assert.equal(h.calls.length, 1);
  h.behavior.overview = () => overview(); pending.resolve(overview()); await flush(); await h.clock.advance();
  assert.equal(h.calls.length, 2); assert.equal(h.peak(), 1);
  for (let i = 100; i < 120; i++) h.controller.invalidate({ type: 'execution.receipt', event_id: i });
  await h.clock.advance(999); assert.equal(h.calls.length, 2);
  await h.clock.advance(1); assert.equal(h.calls.length, 3); h.controller.dispose();
});
test('scope generation clears protected state and ignores late old reads without overlap', async () => {
  const h = harness(), old = deferred(); h.behavior.overview = () => old.promise;
  h.configure(); await h.clock.advance();
  h.configure({ workspace: 'other', identityKey: 'operator2' });
  assert.equal(h.calls[0].signal.aborted, true); assert.equal(h.controller.getState().snapshot, null);
  h.behavior.overview = () => overview({ scope: { workspace_id: 'other' } });
  await h.clock.advance(1000); assert.equal(h.calls.length, 1);
  old.resolve(overview()); await flush(); await h.clock.advance();
  assert.equal(h.controller.getState().snapshot.scope.workspace_id, 'other'); assert.equal(h.peak(), 1); h.controller.dispose();
});
for (const status of [401, 403]) test(`${status} clears visible and paused data and blocks refresh until a new identity`, async () => {
  const h = harness(); h.configure(); await h.clock.advance(); h.controller.pause(true);
  h.behavior.overview = () => { throw error(status); }; h.controller.refresh(); await h.clock.advance(1000);
  assert.equal(h.controller.getState().snapshot, null); assert.equal(h.controller.getState().status, 'forbidden');
  h.controller.apply(); h.controller.refresh(); await h.clock.advance(60000);
  assert.equal(h.calls.length, 2); assert.equal(h.controller.getState().snapshot, null); h.controller.dispose();
});
test('partial failure retains only same-scope stale block, never successful empty or stale forbidden data', async () => {
  const h = harness(); h.configure(); await h.clock.advance();
  h.behavior.overview = () => overview({ work: section([], { status: 'unavailable', total: null, total_is_exact: false }),
    results: section([], { status: 'forbidden', total: null }), external_activity: section([], { status: 'disabled' }) });
  h.controller.refresh(); await h.clock.advance(1000);
  const state = h.controller.getState(); assert.equal(state.status, 'stale');
  assert.deepEqual(state.snapshot.work.items, [{ id: 'work1' }]); assert.equal(state.snapshot.work.total, null);
  assert.equal(state.snapshot.work.status, 'unavailable'); assert.deepEqual(state.snapshot.results.items, []);
  assert.ok(!state.staleSections.includes('external_activity')); h.controller.dispose();
});
test('visual pause keeps published identity and accepts newest snapshot only when applied', async () => {
  const h = harness(); h.configure(); await h.clock.advance(); const original = h.controller.getState().snapshot;
  h.controller.pause(true); h.behavior.overview = () => overview({ snapshot_id: 'new', work: section([{ id: 'work1', title: 'changed' }]) });
  h.controller.refresh(); await h.clock.advance(1000);
  assert.equal(h.controller.getState().snapshot, original); assert.equal(h.controller.getState().hasPendingUpdate, true);
  h.controller.apply(); assert.equal(h.controller.getState().snapshot.snapshot_id, 'new');
  assert.equal(h.controller.getState().paused, true); h.controller.dispose();
});
test('pagination deduplicates immutable IDs; conflict resets via coherent overview instead of replaying cursor', async () => {
  const h = harness(); h.behavior.overview = () => overview({ work: section([{ id: 'work1' }], { next_cursor: 'opaque:1', has_more: true }) });
  h.configure(); await h.clock.advance(); h.behavior.work = () => page([{ id: 'work1' }, { id: 'work2' }], { next_cursor: 'opaque:2', has_more: true });
  h.controller.loadMore('work'); await h.clock.advance(1000);
  assert.deepEqual(h.controller.getState().snapshot.work.items.map(i => i.id), ['work1', 'work2']);
  h.behavior.work = () => { throw error(409); }; h.controller.loadMore('work'); await h.clock.advance(1000);
  await h.clock.advance(1000); assert.deepEqual(h.calls.map(c => c.kind), ['overview', 'work', 'work', 'overview']);
  assert.deepEqual(h.controller.getState().snapshot.work.items.map(i => i.id), ['work1']); h.controller.dispose();
});
test('fallback and source TTL refresh independently of live stream; hidden events reduce work then wake', async () => {
  const h = harness(); h.configure(); await h.clock.advance(); await h.clock.advance(15000); assert.equal(h.calls.length, 2);
  h.behavior.overview = () => overview({ external_activity: section([], { next_refresh_at: '2030-01-01T00:00:02Z' }) });
  h.controller.refresh(); await h.clock.advance(1000); await h.clock.advance(2000); assert.equal(h.calls.length, 4);
  h.configure({ visible: false }); h.controller.invalidate({ type: 'observation.changed', event_id: 9 });
  h.controller.onStreamStatus('reconnecting');
  await h.clock.advance(15000); assert.equal(h.calls.length, 4);
  h.configure({ visible: true }); await h.clock.advance(); assert.equal(h.calls.length, 5); h.controller.dispose();
});

test('returning from background fences sensitive sections until the fresh GET completes', async () => {
  const h = harness(); h.configure(); await h.clock.advance();
  const original = h.controller.getState().snapshot;
  h.configure({ visible: false });
  const pending = deferred(); h.behavior.overview = () => pending.promise;
  h.configure({ visible: true });
  assert.equal(h.controller.getState().status, 'stale');
  assert.ok(h.controller.getState().staleSections.includes('attention'));
  assert.ok(h.controller.getState().staleSections.includes('results'));
  await h.clock.advance(1000);
  assert.equal(h.controller.getState().snapshot, original);
  assert.equal(h.controller.getState().loading, true);
  assert.ok(h.controller.getState().staleSections.includes('results'));
  pending.resolve(overview({ snapshot_id: 'after-background' })); await flush();
  assert.equal(h.controller.getState().status, 'ready');
  assert.equal(h.controller.getState().snapshot.snapshot_id, 'after-background');
  assert.deepEqual(h.controller.getState().staleSections, []);
  h.controller.dispose();
});

test('a GET begun in background cannot clear the wake revalidation fence', async () => {
  const h = harness(); h.configure(); await h.clock.advance();
  h.configure({ visible: false });
  const background = deferred(), fresh = deferred();
  h.behavior.overview = () => background.promise;
  await h.clock.advance(60000); assert.equal(h.calls.length, 2);
  h.behavior.overview = () => fresh.promise;
  h.configure({ visible: true });
  background.resolve(overview({ snapshot_id: 'before-wake' })); await flush();
  assert.equal(h.controller.getState().status, 'stale');
  assert.ok(h.controller.getState().staleSections.includes('results'));
  await h.clock.advance(1000); assert.equal(h.calls.length, 3);
  assert.equal(h.peak(), 1);
  fresh.resolve(overview({ snapshot_id: 'after-wake' })); await flush();
  assert.equal(h.controller.getState().status, 'ready');
  assert.equal(h.controller.getState().snapshot.snapshot_id, 'after-wake');
  h.controller.dispose();
});
test('reconnect/gap invalidate, unrelated events do not, and disposal removes timers', async () => {
  const h = harness(); h.configure(); await h.clock.advance();
  h.controller.invalidate({ type: 'unrelated.diagnostic', event_id: 1 }); await h.clock.advance(1000); assert.equal(h.calls.length, 1);
  h.controller.onStreamStatus('reconnecting'); await h.clock.advance();
  h.controller.onStreamStatus('live'); await h.clock.advance(1000);
  h.controller.invalidate({ type: 'gap', event_id: 10 }); await h.clock.advance(1000); assert.equal(h.calls.length, 4);
  h.controller.dispose(); assert.equal(h.clock.timers.size, 0); await h.clock.advance(60000); assert.equal(h.calls.length, 4);
});
test('wrong-server response is not admitted into the current cache', async () => {
  const h = harness(); h.configure(); await h.clock.advance(); h.behavior.overview = () => overview({ server_id: 'other' });
  h.controller.refresh(); await h.clock.advance(1000); assert.equal(h.controller.getState().snapshot.server_id, 'server');
  assert.equal(h.controller.getState().status, 'stale'); h.controller.dispose();
});
test('Attention pagination reuses canonical category/state/seen cursor contract, not Home display-state', async () => {
  const h = harness(); h.behavior.overview = () => overview({ scope: { workspace_id: 'ws', state: 'running' },
    attention: section([{ attention_id: 'one' }], { next_cursor: 'att:opaque', has_more: true }) });
  h.configure({ state: 'running' }); await h.clock.advance();
  h.behavior.attention = query => ({ version: 1, filters: { workspace_id: query.workspace_id, category: query.category,
    state: query.state, seen: query.seen }, snapshot_revision: 'r1', items: [{ attention_id: 'one' }, { attention_id: 'two' }],
    total: 2, next_cursor: null, observed_at: '2030-01-01T00:00:00Z', next_refresh_at: null });
  h.controller.loadMore('attention'); await h.clock.advance(1000);
  assert.equal(h.calls[1].query.state, 'active'); assert.equal(h.calls[1].query.category, 'action_required');
  assert.equal(h.calls[1].query.seen, 'all'); assert.equal(h.calls[1].query.cursor, 'att:opaque');
  assert.deepEqual(h.controller.getState().snapshot.attention.items.map(x => x.attention_id), ['one', 'two']); h.controller.dispose();
});
test('external generations remain distinct during paginated append and never change native results', async () => {
  const h = harness(), first = { source_id: 'source', observed_instance_id: 'i', generation: 1 };
  h.behavior.overview = () => overview({ external_activity: section([first], { next_cursor: 'ext:1', has_more: true }) });
  h.configure(); await h.clock.advance();
  h.behavior.external = () => page([first, { ...first, generation: 2 }]);
  h.controller.loadMore('external'); await h.clock.advance(1000);
  assert.equal(h.controller.getState().snapshot.external_activity.items.length, 2);
  assert.deepEqual(h.controller.getState().snapshot.results.items, []); h.controller.dispose();
});
test('invalidation matrix and scope keys distinguish external, attention, origin and identity', () => {
  assert.deepEqual(homeInvalidatedSections('observation.activity'), ['external_activity', 'agents', 'attention', 'activity']);
  assert.deepEqual(homeInvalidatedSections('attention-invalidated'), ['attention', 'results', 'work']);
  assert.deepEqual(homeInvalidatedSections('token.delta'), []);
  const context = { workspace: 'all', identityKey: 'A', origin: 'https://one' };
  assert.equal(homeContextKey(context), homeContextKey({ ...context, workspace: null }));
  assert.notEqual(homeContextKey(context), homeContextKey({ ...context, identityKey: 'B' }));
  assert.notEqual(homeContextKey(context), homeContextKey({ ...context, origin: 'https://two' }));
});
test('time spent reading does not extend source TTL by another full interval', async () => {
  const h = harness(), pending = deferred(); h.behavior.overview = () => pending.promise;
  h.configure(); await h.clock.advance(); await h.clock.advance(5000);
  h.behavior.overview = () => overview(); pending.resolve(overview({ work: section([], { next_refresh_at: '2030-01-01T00:00:02Z' }) }));
  await flush(); await h.clock.advance(1000); assert.equal(h.calls.length, 2); h.controller.dispose();
});
test('business feed pages use actual id/kind/agent_id projection and retain distinct records', async () => {
  const h = harness(); h.configure(); await h.clock.advance();
  const event = id => ({ id, kind: 'handoff.created', agent_id: 'A', workspace_id: 'ws', created_at: '2030-01-01T00:00:00Z', label: 'handoff.created' });
  h.behavior.activity = () => page([event('1')], { next_cursor: 'feed:2', has_more: true });
  h.controller.loadMore('activity'); await h.clock.advance(1000);
  h.behavior.activity = () => page([event('1'), event('2')]);
  h.controller.loadMore('activity'); await h.clock.advance(1000);
  assert.deepEqual(h.controller.getState().activity.items.map(i => i.id), ['1', '2']); h.controller.dispose();
});
test('overview refresh retains loaded feed as stale then revalidates first page without old cursor', async () => {
  const h = harness(); h.configure(); await h.clock.advance();
  h.behavior.activity = () => page([{ id: 'old', kind: 'message.created' }], { next_cursor: 'old-cursor', has_more: true });
  h.controller.loadMore('activity'); await h.clock.advance(1000);
  h.behavior.activity = () => page([{ id: 'new', kind: 'message.created' }], { revision: 'r2' });
  h.controller.refresh(); await h.clock.advance(1000);
  assert.deepEqual(h.controller.getState().activity.items.map(i => i.id), ['old']);
  assert.ok(h.controller.getState().staleSections.includes('activity'));
  await h.clock.advance(1000);
  assert.equal(h.calls.at(-1).kind, 'activity'); assert.equal(h.calls.at(-1).query.cursor, undefined);
  assert.deepEqual(h.controller.getState().activity.items.map(i => i.id), ['new']);
  assert.ok(!h.controller.getState().staleSections.includes('activity')); assert.equal(h.peak(), 1); h.controller.dispose();
});
test('modal pause retains expanded pages only for same revision, resets changed revisions, and never crosses scope', async () => {
  const h = harness();
  h.behavior.overview = () => overview({ work: section([{ id: 'one' }], { revision: 'r1', next_cursor: 'p2', has_more: true }) });
  h.configure(); await h.clock.advance();
  h.behavior.work = () => page([{ id: 'two' }], { revision: 'r1', next_cursor: 'p3', has_more: true });
  h.controller.loadMore('work'); await h.clock.advance(1000);
  h.controller.pause(true); h.controller.refresh(); await h.clock.advance(1000); h.controller.pause(false);
  assert.deepEqual(h.controller.getState().snapshot.work.items.map(x => x.id), ['one', 'two']);
  assert.equal(h.controller.getState().snapshot.work.next_cursor, 'p3');
  h.behavior.overview = () => overview({ work: section([{ id: 'changed' }], { revision: 'r2' }) });
  h.controller.pause(true); h.controller.refresh(); await h.clock.advance(1000); h.controller.pause(false);
  assert.deepEqual(h.controller.getState().snapshot.work.items.map(x => x.id), ['changed']);
  assert.match(h.controller.getState().error, /pagination/);
  h.configure({ identityKey: 'other' }); assert.equal(h.controller.getState().snapshot, null);
  await h.clock.advance(1000); assert.deepEqual(h.controller.getState().snapshot.work.items.map(x => x.id), ['changed']);
  h.controller.dispose();
});

test('E02 event during initial snapshot survives its older cursor and queues a fresh canonical read', async () => {
  const h = harness(), first = deferred(), second = deferred();
  h.behavior.overview = () => first.promise;
  h.configure(); await h.clock.advance();
  // Same public entry points invoked by useHomeOverview's stream/event effects.
  h.controller.onStreamStatus('live');
  h.controller.invalidate({ type: 'handoff.completed', event_id: 6 });
  await h.clock.advance(1000); assert.equal(h.calls.length, 1);
  h.behavior.overview = () => second.promise;
  first.resolve(overview({ event_cursor: 5, work: section([{ id: 'work1', display_state: 'running' }]) }));
  await flush(); await h.clock.advance();
  assert.equal(h.calls.length, 2); assert.equal(h.peak(), 1);
  second.resolve(overview({ snapshot_id: 'after-commit', event_cursor: 6,
    work: section([], { revision: 'r2' }), results: section([{ id: 'result1', outcome: 'SUCCEEDED' }], { revision: 'r2' }) }));
  await flush();
  assert.equal(h.controller.getState().snapshot.event_cursor, 6);
  assert.deepEqual(h.controller.getState().snapshot.work.items, []);
  assert.deepEqual(h.controller.getState().snapshot.results.items.map(x => x.id), ['result1']);
  await h.clock.advance(999); assert.equal(h.calls.length, 2);
  h.controller.dispose();
});

test('E02 reconnect and retention gap during a read resnapshot without replaying an obsolete page cursor', async () => {
  const h = harness(), reconnect = deferred();
  h.behavior.overview = () => overview({ work: section([{ id: 'old' }], { next_cursor: 'old-page', has_more: true }) });
  h.configure(); await h.clock.advance();
  h.behavior.overview = () => reconnect.promise;
  h.controller.onStreamStatus('reconnecting'); await h.clock.advance(1000);
  h.controller.onStreamStatus('live');
  h.controller.invalidate({ type: 'gap', event_id: 50 });
  h.controller.loadMore('work');
  h.behavior.overview = () => overview({ event_cursor: 60, event_low_watermark: 50,
    work: section([{ id: 'current', display_state: 'running' }], { revision: 'after-gap' }) });
  reconnect.resolve(overview({ event_cursor: 8,
    work: section([{ id: 'old' }], { next_cursor: 'old-page', has_more: true }) }));
  await flush(); await h.clock.advance(1000);
  assert.deepEqual(h.calls.map(x => x.kind), ['overview', 'overview', 'overview']);
  assert.ok(h.calls.every(x => x.query.cursor === undefined));
  assert.equal(h.peak(), 1);
  assert.equal(h.controller.getState().snapshot.event_low_watermark, 50);
  assert.deepEqual(h.controller.getState().snapshot.work.items.map(x => x.id), ['current']);
  assert.equal(h.controller.getState().snapshot.work.next_cursor, null);
  h.controller.dispose();
});

test('E03 duplicate and out-of-order hints cannot replay activity states over newer canonical snapshots', async () => {
  const h = harness();
  h.behavior.overview = () => overview({ event_cursor: 10,
    work: section([{ id: 'work1', display_state: 'native_accepted' }]) });
  h.configure(); await h.clock.advance();
  h.behavior.overview = () => overview({ event_cursor: 12,
    work: section([{ id: 'work1', display_state: 'running' }], { revision: 'running' }) });
  h.controller.invalidate({ type: 'execution.started', event_id: 12 });
  h.controller.invalidate({ type: 'execution.started', event_id: 12 });
  h.controller.invalidate({ type: 'execution.accepted', event_id: 11 });
  await h.clock.advance(1000);
  assert.equal(h.calls.length, 2);
  assert.deepEqual(h.controller.getState().snapshot.work.items, [{ id: 'work1', display_state: 'running' }]);
  h.behavior.overview = () => overview({ event_cursor: 13,
    work: section([{ id: 'work1', display_state: 'turn_completed' }], { revision: 'terminal' }),
    results: section([{ id: 'result1', outcome: 'SUCCEEDED' }], { revision: 'terminal' }) });
  h.controller.invalidate({ type: 'execution.completed', event_id: 13 });
  await h.clock.advance(1000);
  const terminalIndex = h.changes.length;
  // Old IDs may cause a bounded reread, but event names are never a state reducer.
  for (const [event_id, type] of [[11, 'execution.accepted'], [12, 'execution.started'], [12, 'execution.started'], [10, 'runtime.opened']])
    h.controller.invalidate({ event_id, type });
  await h.clock.advance(1000);
  assert.equal(h.calls.length, 4); assert.equal(h.peak(), 1);
  assert.ok(h.changes.slice(terminalIndex).every(s => s.snapshot.work.items.length === 1 &&
    s.snapshot.work.items[0].display_state === 'turn_completed' && s.snapshot.results.items.length === 1));
  h.controller.dispose();
});

test('E05 a continuously live stream does not renew external TTL or replace stale reported work with native activity', async () => {
  const h = harness(), epoch = Date.parse('2030-01-01T00:00:00Z');
  const iso = ms => new Date(epoch + ms).toISOString();
  const nativeWork = [{ id: 'native', display_state: 'running' }];
  const nativeResult = [{ id: 'native-result', outcome: 'SUCCEEDED' }];
  h.behavior.overview = () => {
    const expired = h.clock.now >= 2000;
    return overview({ generated_at: iso(h.clock.now), work: section(nativeWork), results: section(nativeResult),
      external_activity: section([{ source_id: 'herdr', observed_instance_id: 'reported', generation: 1,
        freshness: expired ? 'stale' : 'current', activity_state: 'working', observational_only: true,
        last_report: { evidence: 'reported', valid_until: iso(2000) } }],
      { as_of: iso(h.clock.now), next_refresh_at: expired ? null : iso(2000), revision: expired ? 'expired' : 'current' }) });
  };
  h.configure(); h.controller.onStreamStatus('live'); await h.clock.advance();
  assert.equal(h.calls.length, 1);
  assert.match(homeExternalLabel(h.controller.getState().snapshot.external_activity.items[0]), /working.*current/);
  await h.clock.advance(1999); assert.equal(h.calls.length, 1);
  h.controller.onStreamStatus('live'); // Same live status cannot extend the deadline.
  await h.clock.advance(1);
  assert.deepEqual(h.calls.map(x => x.at), [0, 2000]);
  const result = h.controller.getState().snapshot;
  assert.equal(result.external_activity.items[0].freshness, 'stale');
  assert.equal(homeExternalLabel(result.external_activity.items[0]), 'External report · state unknown · stale · reported');
  assert.deepEqual(result.work.items, nativeWork); assert.deepEqual(result.results.items, nativeResult);
  h.controller.onStreamStatus('live'); await h.clock.advance(1000);
  assert.equal(h.calls.length, 2); assert.equal(h.peak(), 1);
  h.controller.dispose();
});
