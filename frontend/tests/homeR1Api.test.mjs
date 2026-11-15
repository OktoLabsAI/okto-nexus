import assert from 'node:assert/strict';
import test from 'node:test';
import { moduleURL, overview } from './homeR1Support.mjs';
const canonical = await moduleURL('api.ts');
const navigation = await moduleURL('homeNavigation.ts');
const { homeApi } = await import(await moduleURL('homeApi.ts', { './api': canonical, './homeNavigation': navigation }));

test('Home adapter uses canonical envelope/auth headers, GET-only no-store, encoded filters and opaque target', async () => {
  const original = globalThis.fetch, calls = [];
  globalThis.fetch = async (path, init) => { calls.push({ path, init }); return Response.json({ ok: true, data: overview() }); };
  try {
    const abort = new AbortController(); await homeApi.overview({ workspace_id: 'all' }, abort.signal);
    await homeApi.work({ workspace_id: 'ws/&?', agent_id: 'a:b', cursor: 'opaque=&?#', limit: 10 });
    await homeApi.resolveTarget({ kind: 'message', server_id: 's', workspace_id: 'ws/&?', message_id: 'm:?/&' }, 'ws/&?');
    assert.equal(new URL(calls[0].path, 'https://fixture').searchParams.has('workspace_id'), false);
    assert.equal(new URL(calls[1].path, 'https://fixture').searchParams.get('cursor'), 'opaque=&?#');
    assert.equal(new URL(calls[1].path, 'https://fixture').searchParams.get('workspace_id'), 'ws/&?');
    assert.equal(JSON.parse(new URL(calls[2].path, 'https://fixture').searchParams.get('target')).message_id, 'm:?/&');
    assert.ok(calls.every(c => !c.init.method && c.init.cache === 'no-store' && c.init.headers.get('x-nexus-ui') === '1' && !c.init.body));
    assert.equal(calls[0].init.signal, abort.signal);
  } finally { globalThis.fetch = original; }
});
test('canonical 401 expiry is preserved and an aborted old response cannot expire a new session', async () => {
  const fetch = globalThis.fetch, window = globalThis.window; const events = [];
  globalThis.window = { dispatchEvent: event => events.push(event.type) };
  globalThis.fetch = async () => Response.json({ ok: false, error: { code: 'AUTH_REQUIRED', message: 'fixture' } }, { status: 401 });
  try {
    await assert.rejects(homeApi.overview({}), e => e.status === 401 && e.code === 'AUTH_REQUIRED');
    assert.deepEqual(events, ['nexus-auth-expired']);
    const abort = new AbortController(); abort.abort();
    await assert.rejects(homeApi.overview({}, abort.signal), e => e.name === 'AbortError');
    assert.equal(events.length, 1);
  } finally { globalThis.fetch = fetch; globalThis.window = window; }
});
