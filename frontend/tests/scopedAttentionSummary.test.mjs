import assert from 'node:assert/strict';
import test from 'node:test';
import {moduleURL, Clock, deferred, flush} from './homeR1Support.mjs';
const s = await import(await moduleURL('attentionSummaryState.ts'));
const {ObservationReader} = await import(await moduleURL('observationReader.ts'));
const summary = (workspace = 'project-a', patch = {}) => ({version:1, filters:{workspace_id:workspace,state:'active',seen:'all'},
  total:2, counts:{action_required:1,watch:1,priority:{10:1,20:1,30:0},unseen:2,snoozed:0},event_cursor:1,event_low_watermark:1,
  snapshot_revision:'rev1',observed_at:'2026-11-16T00:00:00Z',next_refresh_at:'2026-11-16T00:00:15Z',refresh_after_seconds:15,...patch});
const read = (value, status = 'ready', patch = {}) => ({key:'key',value,status,loading:false,error:null,...patch});
function harness() {
  const clock = new Clock(), calls = [];
  const behavior = {read: query => summary(query.workspace_id)};
  const reader = new ObservationReader({read:(query,signal)=>{calls.push({query,signal});return Promise.resolve().then(()=>behavior.read(query));},
    refreshAfter:s.attentionSummaryRefreshAfter, now:()=>clock.now,setTimeout:clock.set,clearTimeout:clock.clear,onChange:()=>{}});
  return {clock,calls,reader,behavior};
}

test('scoped query supports all without workspace_id, disables off, and fixes active/all filters', () => {
  assert.deepEqual(s.scopedAttentionSummaryQuery('all',true),{state:'active',seen:'all'});
  assert.equal(s.scopedAttentionSummaryQuery('project-a',false),null);
  assert.equal(s.scopedAttentionSummaryQuery('',true),null);
  assert.deepEqual(s.scopedAttentionSummaryQuery('project-a',true),{workspace_id:'project-a',state:'active',seen:'all'});
  const global=summary('project-a',{filters:{state:'active',seen:'all'}});
  assert.equal(s.scopedAttentionSummaryState(read(global),'all').status,'ready');
  assert.equal(s.scopedAttentionSummaryState(read(summary()),'all').summary,null);
  assert.equal(s.scopedAttentionSummaryState(read(global),'project-a').summary,null);
});

test('adapter never exposes a summary from another project or incompatible filters', () => {
  for (const value of [summary('project-b'),summary(undefined,{filters:{state:'active',seen:'all'}}),summary('project-a',{filters:{workspace_id:'project-a',state:'all',seen:'all'}})]) {
    const state=s.scopedAttentionSummaryState(read(value),'project-a');
    assert.equal(state.summary,null);assert.equal(state.status,'error');assert.equal(state.page,null);
  }
});

test('ready and stale keep only the scoped summary; forbidden/unavailable clear and use attention copy', () => {
  const value=summary();
  assert.equal(s.scopedAttentionSummaryState(read(value),'project-a').summary,value);
  const stale=s.scopedAttentionSummaryState(read(value,'stale',{loading:true,error:'External observations internal error'}),'project-a');
  assert.equal(stale.status,'stale');assert.equal(stale.loading,true);assert.equal(stale.summary,value);
  assert.equal(stale.page,null);assert.deepEqual(stale.pendingIds,[]);assert.equal(stale.streamStatus,'off');
  assert.doesNotMatch(stale.error,/External observations/);
  for (const status of ['forbidden','unavailable','error']) {
    const state=s.scopedAttentionSummaryState(read(value,status),'project-a');
    assert.equal(state.summary,null);assert.equal(state.status,status==='forbidden'?'forbidden':'error');
    assert.doesNotMatch(state.error,/External observation/);
  }
});

test('summary freshness respects shorter or expired server TTL and never extends beyond 15 seconds', () => {
  assert.equal(s.attentionSummaryRefreshAfter(summary('project-a',{refresh_after_seconds:30})),15);
  assert.equal(s.attentionSummaryRefreshAfter(summary('project-a',{refresh_after_seconds:0.25})),0.25);
  assert.equal(s.attentionSummaryRefreshAfter(summary('project-a',{refresh_after_seconds:0})),0);
  assert.equal(s.attentionSummaryRefreshAfter(summary('project-a',{refresh_after_seconds:NaN})),0);
});

test('actual passive reader aborts A on B and ignores late A while adapter rejects crossed payloads', async () => {
  const h=harness(), old=deferred();h.behavior.read=query=>query.workspace_id==='project-a'?old.promise:summary('project-b');
  h.reader.configure(s.scopedAttentionSummaryQuery('project-a',true));await flush();
  h.reader.configure(s.scopedAttentionSummaryQuery('project-b',true));await flush();
  assert.equal(h.calls[0].signal.aborted,true);
  old.resolve(summary('project-a'));await flush();
  const state=s.scopedAttentionSummaryState(h.reader.getState(),'project-b');
  assert.equal(state.summary.filters.workspace_id,'project-b');assert.equal(state.status,'ready');
  assert.equal(s.scopedAttentionSummaryState(read(summary('project-a')),'project-b').summary,null);
  h.reader.dispose();
});

test('actual reader polls by 15 seconds without a stream and auth clear cancels polling', async () => {
  const h=harness();h.reader.configure(s.scopedAttentionSummaryQuery('project-a',true));await flush();
  await h.clock.advance(14999);assert.equal(h.calls.length,1);
  await h.clock.advance(1);assert.equal(h.calls.length,2);
  h.reader.clear();assert.equal(s.scopedAttentionSummaryState(h.reader.getState(),'project-a').summary,null);
  assert.equal(s.scopedAttentionSummaryState(h.reader.getState(),'project-a').status,'forbidden');
  await h.clock.advance(60000);assert.equal(h.calls.length,2);h.reader.dispose();
});

test('actual reader disabling summary aborts in-flight request and adapter exposes no old count', async () => {
  const h=harness(), pending=deferred();h.behavior.read=()=>pending.promise;
  h.reader.configure(s.scopedAttentionSummaryQuery('project-a',true));await flush();
  h.reader.configure(s.scopedAttentionSummaryQuery('project-a',false));
  assert.equal(h.calls[0].signal.aborted,true);pending.resolve(summary());await flush();
  assert.equal(h.reader.getState().value,null);
  const state=s.scopedAttentionSummaryState(h.reader.getState(),'project-a',false);assert.equal(state.status,'disabled');assert.equal(state.summary,null);
  h.reader.dispose();
});
