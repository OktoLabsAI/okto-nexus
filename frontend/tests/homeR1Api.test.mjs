import assert from 'node:assert/strict';
import test from 'node:test';
import { moduleURL, overview } from './homeR1Support.mjs';
const canonical = await moduleURL('api.ts');
const navigation = await moduleURL('homeNavigation.ts');
const { homeApi } = await import(await moduleURL('homeApi.ts', { './api': canonical, './homeNavigation': navigation }));

test('board root and exact column are one passive API family with scoped opaque cursor and no quick tab',async()=>{
  const original=globalThis.fetch,calls=[];globalThis.fetch=async(path,init)=>{calls.push({path,init});return Response.json({ok:true,data:{}});};
  try{
    const abort=new AbortController(),query={workspace_id:'project/&?',agent_id:'agent',host:'host',harness:'codex_app_server',limit:10,preview:3};
    await homeApi.board(query,abort.signal);await homeApi.boardColumn('needs_you',{...query,cursor:'opaque:/&?'},abort.signal);
    assert.deepEqual(calls.map(c=>new URL(c.path,'http://fixture').pathname),['/api/v1/home/board','/api/v1/home/board/needs_you']);
    assert.equal(new URL(calls[1].path,'http://fixture').searchParams.get('cursor'),'opaque:/&?');
    for(const c of calls){assert.equal(new URL(c.path,'http://fixture').searchParams.has('quick'),false);assert.equal(c.init.signal,abort.signal);assert.equal(c.init.cache,'no-store');assert.equal(c.init.method,undefined);assert.equal(c.init.body,undefined);}
  }finally{globalThis.fetch=original;}
});

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

test('unified entries and every child partition preserve encoded parents and use the canonical passive adapter',async()=>{
  const original=globalThis.fetch,calls=[];
  globalThis.fetch=async(path,init)=>{calls.push({path,init});return Response.json({ok:true,data:{}});};
  try{
    const query={workspace_id:'ws/&?',quick:'needs_you',harness:'codex_app_server',host:'host:/one',cursor:'opaque=&?#',limit:10,preview:3};
    const group='group:/&?',entry='entry:/&?';
    await homeApi.entries(query);await homeApi.entryChildren(group,query);await homeApi.entrySessions(group,entry,query);
    await homeApi.entryAttention(group,entry,query);await homeApi.entryResults(group,entry,query);
    assert.deepEqual(calls.map(c=>new URL(c.path,'https://fixture').pathname),[
      '/api/v1/home/entries',`/api/v1/home/entries/${encodeURIComponent(group)}/children`,
      ...['sessions','attention','results'].map(kind=>`/api/v1/home/entries/${encodeURIComponent(group)}/children/${encodeURIComponent(entry)}/${kind}`)]);
    for(const c of calls){
      const url=new URL(c.path,'https://fixture');for(const [key,value]of Object.entries(query))assert.equal(url.searchParams.get(key),String(value));
      assert.equal(c.init.cache,'no-store');assert.equal(c.init.method,undefined);assert.equal(c.init.body,undefined);assert.equal(c.init.headers.get('x-nexus-ui'),'1');
    }
    await homeApi.entries({workspace_id:'all'});const defaultQuery=new URL(calls.at(-1).path,'https://fixture').searchParams;
    assert.equal(defaultQuery.has('quick'),false);assert.equal(defaultQuery.has('workspace_id'),false);
  }finally{globalThis.fetch=original;}
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

test('project and Server attention have separate read-only Home cursor endpoints', async () => {
  const original=globalThis.fetch,calls=[];
  globalThis.fetch=async(path,init)=>{calls.push({path,init});return Response.json({ok:true,data:{}});};
  try{
    const query={workspace_id:'ws/?',agent_id:'agent',state:'running',cursor:'opaque=&?',limit:20};
    await homeApi.attention(query);await homeApi.server_attention(query);
    assert.deepEqual(calls.map(c=>new URL(c.path,'https://fixture').pathname),['/api/v1/home/attention','/api/v1/home/server-attention']);
    for(const c of calls){
      const url=new URL(c.path,'https://fixture');
      for(const [key,value]of Object.entries(query))assert.equal(url.searchParams.get(key),String(value));
      assert.equal(c.init.cache,'no-store');assert.equal(c.init.method,undefined);assert.equal(c.init.body,undefined);
    }
  }finally{globalThis.fetch=original;}
});
