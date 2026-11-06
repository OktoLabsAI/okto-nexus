import {readFile} from 'node:fs/promises';
import assert from 'node:assert/strict';
import test from 'node:test';
import ts from 'typescript';

const source = await readFile(new URL('../src/api.ts', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, {compilerOptions: {
  module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022,
}}).outputText;
const {api} = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`);
const response = (data = {}) => new Response(JSON.stringify({ok: true, data}), {status: 200});

async function capture(run) {
  const old = globalThis.fetch;
  const requests = [];
  globalThis.fetch = async (url, init) => {requests.push({url, init}); return response();};
  try {await run(requests);} finally {globalThis.fetch = old;}
}

test('attention page and summary preserve scoped filters and opaque cursor', async () => {
  await capture(async requests => {
    const controller = new AbortController();
    await api.attention({workspace_id: 'w / a', agent_id: 'a&b', state: 'all', seen: 'snoozed',
      priority: 30, limit: 50, cursor: 'opaque+/=token'}, controller.signal);
    await api.attentionSummary({workspace_id: 'w / a', state: 'active'}, controller.signal);
    const page = new URL(requests[0].url, 'https://nexus.test');
    assert.equal(page.pathname, '/api/v1/attention');
    assert.equal(page.searchParams.get('workspace_id'), 'w / a');
    assert.equal(page.searchParams.get('agent_id'), 'a&b');
    assert.equal(page.searchParams.get('cursor'), 'opaque+/=token');
    assert.equal(page.searchParams.get('priority'), '30');
    const summary = new URL(requests[1].url, 'https://nexus.test');
    assert.equal(summary.pathname, '/api/v1/attention/summary');
    assert.equal(summary.searchParams.has('cursor'), false);
    assert.equal(summary.searchParams.has('limit'), false);
    assert.equal(requests[0].init.signal, controller.signal);
    assert.equal(requests[0].init.cache, 'no-store');
    assert.equal(requests[0].init.headers.get('x-nexus-ui'), '1');
  });
});

test('viewing preferences and canonical approvals send their separate revision fences', async () => {
  await capture(async requests => {
    const fence = {source_revision: 'source-revision', preference_revision: 3};
    await api.attentionSeen('attention/id', {...fence, seen: false});
    await api.attentionSnooze('attention/id', {...fence, until: null});
    await api.decideApproval('approval/id', 'reject', 'Reviewed current request', undefined, 7);
    assert.equal(requests[0].url, '/api/v1/attention/attention%2Fid/seen');
    assert.deepEqual(JSON.parse(requests[0].init.body), {...fence, seen: false});
    assert.deepEqual(JSON.parse(requests[1].init.body), {...fence, until: null});
    assert.deepEqual(JSON.parse(requests[2].init.body), {
      decision: 'reject', justification: 'Reviewed current request', expected_decision_revision: 7,
    });
    assert.ok(requests.every(request => request.init.method === 'POST'));
  });
});

test('exact operation and cleanup inspection send no productive action', async () => {
  await capture(async requests => {
    await api.runtimeOperationInspection('operation/older');
    await api.inspectRuntimeMaintenance('maintenance/older');
    assert.equal(requests[0].url, '/api/v1/harness/outbox?operation_id=operation%2Folder');
    assert.equal(requests[0].init.method, undefined);
    assert.deepEqual(JSON.parse(requests[1].init.body), {
      action: 'inspect', maintenance_id: 'maintenance/older',
    });
  });
});

test('a late unauthorized response from an aborted scope cannot expire a newer session', async () => {
  const oldFetch = globalThis.fetch, oldWindow = globalThis.window;
  const events = [];
  globalThis.window = {dispatchEvent: event => events.push(event.type)};
  let finish;
  globalThis.fetch = () => new Promise(resolve => {finish = resolve;});
  try {
    const controller = new AbortController();
    const pending = api.attention({}, controller.signal);
    controller.abort();
    finish(new Response(JSON.stringify({ok: false, error: {code: 'AUTH_FAILED', message: 'Expired'}}), {status: 401}));
    await assert.rejects(pending, {name: 'AbortError'});
    assert.deepEqual(events, []);
    globalThis.fetch = async () => new Response(JSON.stringify({ok: false,
      error: {code: 'AUTH_FAILED', message: 'Expired'}}), {status: 401});
    await assert.rejects(api.attention(), {status: 401, code: 'AUTH_FAILED'});
    assert.deepEqual(events, ['nexus-auth-expired']);
  } finally {globalThis.fetch = oldFetch; globalThis.window = oldWindow;}
});
