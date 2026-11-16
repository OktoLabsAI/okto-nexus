import assert from 'node:assert/strict';
import test from 'node:test';
import {moduleURL,Clock,deferred,flush,overview} from './homeR1Support.mjs';
const {HomeController,homeEntryPageKey}=await import(await moduleURL('homeController.ts'));
const now='2026-11-16T12:00:00Z';
const session=id=>({server_id:'server',executor_id:'executor',workspace_id:'ws',session_id:id});
const entry=(id='e1',patch={})=>({id,kind:'work',workspace_id:'ws',agent_id:'A',source_ref:{type:'handoff',id,revision:'r'},title:id,
  sessions:[session('s1')],sessions_total:2,has_more_sessions:true,sessions_cursor:'sessions-cursor',
  attention_preview:[],attention_total:0,has_more_attention:false,attention_cursor:null,results_preview:[],results_total:0,has_more_results:false,results_cursor:null,...patch});
const group=(id='g1',patch={})=>({id,server_id:'server',workspace_id:'ws',agent_id:'A',connection:null,label:id,
  children:[entry()],children_total:2,has_more_children:true,children_cursor:'children-cursor',...patch});
const page=(query={},patch={})=>({version:1,server_id:'server',scope:{workspace_id:query.workspace_id??null,quick:query.quick??'active',include_recent_results:query.quick===undefined,
  ...(query.agent_id?{agent_id:query.agent_id}:{}),...(query.state?{state:query.state}:{}),...(query.harness?{harness:query.harness}:{}),...(query.host?{host:query.host}:{})},
  partition:'groups',group_id:null,entry_id:null,status:'ready',items:[group()],total:1,total_is_exact:true,has_more:false,next_cursor:null,
  generated_at:now,as_of:now,next_refresh_at:'2026-11-16T12:00:15Z',snapshot_id:'r1',revision:'r1',event_cursor:1,event_low_watermark:1,
  source_status:{work:'ready',results:'ready',attention:'ready',sessions:'ready',connections:'ready',correlations:'ready',external:'disabled'},
  coverage:{result_tracking:'ready'},summary:{},server_attention:{status:'ready',items:[],total:0,total_is_exact:true,has_more:false},...patch});
function harness(){
  const clock=new Clock(),calls=[];let active=0,peak=0;
  const behavior={entries:q=>page(q),entryChildren:(g,q)=>page(q,{partition:'children',group_id:g,items:[entry('e2')]}),
    entrySessions:(g,e,q)=>page(q,{partition:'sessions',group_id:g,entry_id:e,items:[session('s1'),session('s2')]}),
    entryAttention:(g,e,q)=>page(q,{partition:'attention',group_id:g,entry_id:e,items:[]}),
    entryResults:(g,e,q)=>page(q,{partition:'results',group_id:g,entry_id:e,items:[]}),overview:()=>overview()};
  const api=Object.fromEntries(Object.keys(behavior).map(kind=>[kind,async(...args)=>{const signal=args.at(-1);calls.push({kind,args,signal,at:clock.now});active++;peak=Math.max(peak,active);
    try{return await behavior[kind](...args.slice(0,-1));}finally{active--;}}]));
  const controller=new HomeController({api,now:()=>clock.now,setTimeout:clock.set,clearTimeout:clock.clear});
  const configure=(patch={})=>controller.configure({family:'entries',workspace:'ws',identityKey:'operator',origin:'http://fixture',visible:true,enabled:true,...patch});
  return {controller,configure,clock,calls,behavior,peak:()=>peak};
}

test('entries uses the same serialized burst queue and preserves event received during initial snapshot',async()=>{
  const h=harness(),pending=deferred();h.behavior.entries=()=>pending.promise;h.configure();await h.clock.advance();
  for(let i=0;i<80;i++)h.controller.invalidate({type:'execution.receipt',event_id:i});
  await h.clock.advance(1000);assert.equal(h.calls.length,1);
  h.behavior.entries=q=>page(q);pending.resolve(page({workspace_id:'ws'},{event_cursor:0}));await flush();
  assert.equal(h.controller.getState().status,'stale');await h.clock.advance();
  assert.equal(h.calls.length,2);assert.equal(h.peak(),1);assert.ok(h.calls.every(c=>c.kind==='entries'));h.controller.dispose();
});

test('family, identity and exact quick defaults fence old reads before exposing new state',async()=>{
  const h=harness(),pending=deferred();h.behavior.entries=()=>pending.promise;h.configure();await h.clock.advance();
  h.configure({quick:'active',identityKey:'new'});assert.equal(h.calls[0].signal.aborted,true);assert.equal(h.controller.getState().entries,null);
  h.behavior.entries=q=>page(q);pending.resolve(page({workspace_id:'ws'}));await flush();await h.clock.advance(1000);
  assert.equal(h.calls[1].args[0].quick,'active');assert.equal(h.controller.getState().entries.scope.include_recent_results,false);
  h.configure({family:'legacy'});await h.clock.advance(1000);assert.equal(h.calls.at(-1).kind,'overview');assert.equal(h.controller.getState().entries,null);
  assert.ok(h.controller.getState().snapshot);h.controller.dispose();
});

test('group and session pagination bind parents/revision and append immutable identities only',async()=>{
  const h=harness();h.configure();await h.clock.advance();
  h.controller.loadGroupChildren('g1');await h.clock.advance(1000);
  assert.equal(h.calls[1].args[1].cursor,'children-cursor');assert.deepEqual(h.controller.getState().entryChildren.g1.items.map(x=>x.id),['e1','e2']);
  h.controller.loadEntrySessions('g1','e1');await h.clock.advance(1000);
  assert.equal(h.calls[2].args[2].cursor,'sessions-cursor');
  assert.deepEqual(h.controller.getState().entrySessions[homeEntryPageKey('g1','e1')].items.map(x=>x.session_id),['s1','s2']);
  assert.equal(h.peak(),1);h.controller.dispose();
});

test('foreign server/parent response is not admitted, and409 resnapshots without replaying an action',async()=>{
  const h=harness();h.configure();await h.clock.advance();
  h.behavior.entrySessions=(g,e,q)=>page(q,{partition:'sessions',group_id:'foreign',entry_id:e,items:[session('wrong')]});
  h.controller.loadEntrySessions('g1','e1');await h.clock.advance(1000);assert.deepEqual(h.controller.getState().entrySessions,{});
  h.behavior.entrySessions=(g,e,q)=>page(q,{partition:'sessions',group_id:g,entry_id:e,server_id:'foreign-server',items:[session('wrong')]});
  h.controller.loadEntrySessions('g1','e1');await h.clock.advance(1000);assert.deepEqual(h.controller.getState().entrySessions,{});
  h.behavior.entrySessions=()=>{throw Object.assign(Error('changed'),{status:409});};
  h.controller.loadEntrySessions('g1','e1');await h.clock.advance(1000);await h.clock.advance(1000);
  assert.equal(h.calls.at(-1).kind,'entries');assert.ok(h.calls.every(c=>['entries','entrySessions'].includes(c.kind)));h.controller.dispose();
});

for(const status of [401,403])test(`${status} clears every paused entries cache and blocks repeated reads`,async()=>{
  const h=harness();h.configure();await h.clock.advance();h.controller.loadEntrySessions('g1','e1');await h.clock.advance(1000);
  h.controller.pause(true);h.behavior.entries=()=>{throw Object.assign(Error('denied'),{status});};h.controller.refresh();await h.clock.advance(1000);
  assert.equal(h.controller.getState().status,'forbidden');assert.equal(h.controller.getState().entries,null);assert.deepEqual(h.controller.getState().entrySessions,{});
  const n=h.calls.length;h.controller.refresh();await h.clock.advance(60000);assert.equal(h.calls.length,n);h.controller.dispose();
});

test('paused group order remains stable until apply and changed revision clears parent pages',async()=>{
  const h=harness();h.configure();await h.clock.advance();h.controller.loadGroupChildren('g1');await h.clock.advance(1000);h.controller.pause(true);
  h.behavior.entries=q=>page(q,{revision:'r2',items:[group('g2'),group('g1')]});h.controller.refresh();await h.clock.advance(1000);
  assert.deepEqual(h.controller.getState().entries.items.map(x=>x.id),['g1']);assert.equal(h.controller.getState().hasPendingUpdate,true);
  h.controller.pause(false);assert.deepEqual(h.controller.getState().entries.items.map(x=>x.id),['g2','g1']);assert.deepEqual(h.controller.getState().entryChildren,{});h.controller.dispose();
});

test('live SSE cannot extend TTL, and background wake revalidates before displaying old actions',async()=>{
  const h=harness();h.behavior.entries=q=>page(q,{next_refresh_at:'2026-11-16T12:00:02Z'});h.configure();await h.clock.advance();h.controller.onStreamStatus('live');await h.clock.advance(1000);
  const n=h.calls.length;await h.clock.advance(2000);assert.ok(h.calls.length>n);
  h.configure({visible:false});h.controller.invalidate({type:'handoff.created',event_id:100});const hidden=h.calls.length;await h.clock.advance(5000);assert.equal(h.calls.length,hidden);
  h.configure({visible:true});assert.equal(h.controller.getState().status,'stale');await h.clock.advance(1000);assert.equal(h.controller.getState().status,'ready');h.controller.dispose();
});

test('holding order keeps exact group membership and blocks old cursor until explicit apply',async()=>{
  const h=harness();h.configure();await h.clock.advance();h.controller.holdOrder(true);
  const generation=h.controller.getState().generation;
  h.behavior.entries=q=>page(q,{revision:'r2',items:[group('new-group',{children:[entry('e1')]})]});
  h.controller.refresh();await h.clock.advance(1000);
  assert.equal(h.controller.getState().generation,generation);assert.equal(h.controller.getState().entries.items[0].id,'g1');
  assert.equal(h.controller.getState().entries.items[0].children[0].id,'e1');assert.equal(h.controller.getState().hasPendingUpdate,true);
  const n=h.calls.length;h.controller.loadGroupChildren('g1');await h.clock.advance(1000);assert.equal(h.calls.length,n);
  h.controller.apply();assert.equal(h.controller.getState().entries.items[0].id,'new-group');assert.equal(h.controller.getState().entries.items[0].children[0].id,'e1');
  assert.equal(h.controller.getState().status,'ready');h.controller.dispose();
});

test('stable held rows accept text updates, but a new revision cannot discard expanded child pages',async()=>{
  const h=harness();h.configure();await h.clock.advance();h.configure({holdOrder:true});
  h.behavior.entries=q=>page(q,{revision:'r2',items:[group('g1',{children:[entry('e1',{title:'Updated title'})]})]});
  h.controller.refresh();await h.clock.advance(1000);assert.equal(h.controller.getState().entries.items[0].children[0].title,'Updated title');assert.equal(h.controller.getState().hasPendingUpdate,false);
  h.behavior.entryChildren=(g,q)=>page(q,{partition:'children',group_id:g,revision:'r2',items:[entry('e2')]});
  h.controller.loadGroupChildren('g1');await h.clock.advance(1000);assert.equal(h.controller.getState().entryChildren.g1.items.length,2);
  h.behavior.entries=q=>page(q,{revision:'r3',items:[group('g1',{children:[entry('e1',{title:'Third revision'})]})]});
  h.controller.refresh();await h.clock.advance(1000);assert.equal(h.controller.getState().entryChildren.g1.items.length,2);assert.equal(h.controller.getState().hasPendingUpdate,true);
  h.controller.apply();assert.deepEqual(h.controller.getState().entryChildren,{});assert.equal(h.controller.getState().entries.revision,'r3');h.controller.dispose();
});

test('partial totals remain unknown and unavailable data is retained only as explicit same-scope stale content',async()=>{
  const h=harness();h.configure();await h.clock.advance();
  h.behavior.entries=q=>page(q,{status:'partial',revision:'partial',total:null,total_is_exact:false,source_status:{work:'ready',attention:'unavailable'}});
  h.controller.refresh();await h.clock.advance(1000);assert.equal(h.controller.getState().entries.total,null);assert.equal(h.controller.getState().status,'stale');assert.equal(h.controller.getState().entries.items.length,1);
  h.behavior.entries=q=>page(q,{status:'unavailable',revision:null,as_of:'2026-11-16T12:01:00Z',total:null,total_is_exact:false,items:[],source_status:{work:'unavailable',attention:'unavailable'}});
  h.controller.refresh();await h.clock.advance(1000);assert.equal(h.controller.getState().entries.status,'unavailable');assert.equal(h.controller.getState().entries.items[0].id,'g1');assert.equal(h.controller.getState().entries.has_more,false);assert.equal(h.controller.getState().entries.as_of,now);
  h.configure({workspace:'other'});assert.equal(h.controller.getState().entries,null);h.controller.dispose();
});

test('connection and workspace context hints invalidate entries through the existing coalesced queue',async()=>{
  const h=harness();h.configure();await h.clock.advance();
  h.controller.invalidate({type:'connection.configured',event_id:2});h.controller.invalidate({type:'workspace.updated',event_id:3});
  assert.equal(h.controller.getState().status,'stale');await h.clock.advance(1000);assert.equal(h.calls.length,2);assert.equal(h.peak(),1);h.controller.dispose();
});

test('related attention/results use entry-specific cursors without changing group inventory',async()=>{
  const h=harness();h.behavior.entries=q=>page(q,{items:[group('g1',{children:[entry('e1',{
    attention_preview:[{attention_id:'a1'}],attention_total:2,has_more_attention:true,attention_cursor:'attention-cursor',
    results_preview:[{id:'r1'}],results_total:2,has_more_results:true,results_cursor:'results-cursor'})]})]});
  h.behavior.entryAttention=(g,e,q)=>page(q,{partition:'attention',group_id:g,entry_id:e,items:[{attention_id:'a1'},{attention_id:'a2'}]});
  h.behavior.entryResults=(g,e,q)=>page(q,{partition:'results',group_id:g,entry_id:e,items:[{id:'r1'},{id:'r2'}]});
  h.configure();await h.clock.advance();h.controller.loadEntryAttention('g1','e1');await h.clock.advance(1000);
  h.controller.loadEntryResults('g1','e1');await h.clock.advance(1000);
  assert.equal(h.calls[1].args[2].cursor,'attention-cursor');assert.equal(h.calls[2].args[2].cursor,'results-cursor');
  const key=homeEntryPageKey('g1','e1'),state=h.controller.getState();
  assert.deepEqual(state.entryAttention[key].items.map(x=>x.attention_id),['a1','a2']);assert.deepEqual(state.entryResults[key].items.map(x=>x.id),['r1','r2']);
  assert.deepEqual(state.entries.items.map(x=>x.id),['g1']);assert.equal(h.peak(),1);h.controller.dispose();
});
