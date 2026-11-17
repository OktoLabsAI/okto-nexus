import assert from 'node:assert/strict';
import test from 'node:test';
import {moduleURL,Clock,deferred,flush} from './homeR1Support.mjs';
const {HomeController,homeEntryPageKey}=await import(await moduleURL('homeController.ts'));
const now='2026-11-16T12:00:00Z';
const entry=(id='work',revision='e1',workspace='ws')=>({id,group_id:'group',entry_revision:revision,workspace_id:workspace,
  sessions:[],sessions_total:2,has_more_sessions:true,sessions_cursor:'sessions-cursor',attention_refs:[],result_refs:[],
  attention_preview:[],attention_total:0,has_more_attention:false,attention_cursor:null,results_preview:[],results_total:0,has_more_results:false,results_cursor:null,target:null});
const slice=(items=[],patch={})=>({items,total:items.length,total_is_exact:true,has_more:false,next_cursor:null,...patch});
const board=(query={},patch={})=>({version:1,partition:'board',server_id:'server',scope:{workspace_id:query.workspace_id??null,quick:'all',include_recent_results:false,
  ...(query.agent_id?{agent_id:query.agent_id}:{}),...(query.state?{state:query.state}:{}),...(query.harness?{harness:query.harness}:{}),...(query.host?{host:query.host}:{})},
  status:'ready',revision:'b1',entry_revision:'e1',snapshot_id:'b1',generated_at:now,as_of:now,next_refresh_at:'2026-11-16T12:00:15Z',event_cursor:1,event_low_watermark:1,
  source_status:{work:'ready',results:'ready',attention:'ready',sessions:'ready',connections:'ready',correlations:'ready',external:'disabled'},coverage:{result_tracking:'ready'},summary:{},
  server_attention:{status:'ready',items:[],total:0,total_is_exact:true,has_more:false},
  columns:{active:slice([entry('work','e1',query.workspace_id??'ws')],{total:2,has_more:true,next_cursor:'active-cursor'}),needs_you:slice(),results:slice()},...patch});
const column=(name,query={},patch={})=>{const {columns,...metadata}=board(query);return {...metadata,partition:'board_column',column:name,...slice([entry('work2')],{total:2}),...patch};};
function harness(){
  const clock=new Clock(),calls=[];let active=0,peak=0;
  const behavior={board:q=>board(q),boardColumn:(name,q)=>column(name,q),
    entrySessions:(group,id,q)=>({...board(q),partition:'sessions',group_id:group,entry_id:id,revision:'e1',...slice([{server_id:'server',executor_id:'executor',workspace_id:'ws',session_id:'session2'}])})};
  const api=Object.fromEntries(Object.keys(behavior).map(name=>[name,async(...args)=>{
    const signal=args.at(-1);calls.push({name,args:args.slice(0,-1),signal});active++;peak=Math.max(peak,active);
    try{return await behavior[name](...args.slice(0,-1));}finally{active--;}
  }]));
  const controller=new HomeController({api,now:()=>clock.now,setTimeout:clock.set,clearTimeout:clock.clear});
  const configure=patch=>controller.configure({family:'board',workspace:'ws',identityKey:'operator',origin:'http://fixture',visible:true,...patch});
  return {clock,calls,behavior,controller,configure,peak:()=>peak};
}

test('one board read and explicit column append reuse the serialized queue; related pages use entry revision',async()=>{
  const h=harness();h.configure();await h.clock.advance();
  assert.deepEqual(h.calls.map(x=>x.name),['board']);assert.equal('quick' in h.calls[0].args[0],false);
  h.controller.holdOrder(true);h.controller.loadBoardColumn('active');await h.clock.advance(1000);
  assert.deepEqual(h.controller.getState().board.columns.active.items.map(x=>x.id),['work','work2']);
  assert.equal(h.controller.getState().hasPendingUpdate,false);
  h.controller.loadEntrySessions('group','work');await h.clock.advance(1000);
  assert.equal(h.calls.at(-1).args[2].quick,'all');
  assert.equal(h.controller.getState().entrySessions[homeEntryPageKey('group','work')].revision,'e1');
  assert.equal(h.peak(),1);h.controller.dispose();
});

test('a new global revision moves one card once and resets all loaded columns and related pages',async()=>{
  const h=harness();h.configure();await h.clock.advance();
  h.controller.loadBoardColumn('active');await h.clock.advance(1000);
  h.controller.loadEntrySessions('group','work');await h.clock.advance(1000);
  const next=board({workspace_id:'ws'},{revision:'b2',entry_revision:'e2',snapshot_id:'b2',columns:{active:slice([entry('new-active','e2')]),needs_you:slice([entry('work','e2')]),results:slice()}});
  h.behavior.board=()=>next;h.controller.refresh();await h.clock.advance(1000);
  const state=h.controller.getState();assert.deepEqual(state.board.columns.active.items.map(x=>x.id),['new-active']);
  assert.deepEqual(state.board.columns.needs_you.items.map(x=>x.id),['work']);
  assert.equal(Object.values(state.board.columns).flatMap(x=>x.items).filter(x=>x.id==='work').length,1);
  assert.deepEqual(state.entrySessions,{});assert.equal(state.board.columns.active.next_cursor,null);h.controller.dispose();
});

test('409 in one column closes every cursor before a full board resnapshot, never appending moved work',async()=>{
  const h=harness();h.configure();await h.clock.advance();
  h.behavior.boardColumn=()=>{throw Object.assign(Error('changed'),{status:409});};
  h.behavior.board=q=>board(q,{revision:'b2',entry_revision:'e2',columns:{active:slice(),needs_you:slice([entry('work','e2')]),results:slice()}});
  h.controller.loadBoardColumn('active');await h.clock.advance(1000);
  assert.ok(Object.values(h.controller.getState().board.columns).every(x=>x.next_cursor===null));
  h.controller.loadBoardColumn('active');await h.clock.advance(1000);
  assert.deepEqual(h.calls.map(x=>x.name),['board','boardColumn','board']);
  assert.equal(h.controller.getState().board.columns.active.items.length,0);
  assert.equal(h.controller.getState().board.columns.needs_you.items[0].id,'work');h.controller.dispose();
});

test('an enqueued old column cursor is discarded when a stream invalidation requests a new snapshot',async()=>{
  const h=harness();h.configure();await h.clock.advance();h.controller.loadBoardColumn('active');
  h.controller.invalidate({type:'native.requested',event_id:2});await h.clock.advance(1000);
  assert.deepEqual(h.calls.map(x=>x.name),['board','board']);h.controller.dispose();
});

test('late403 from aborted scope cannot revoke the new board, and focus/pause do not publish moved rows',async()=>{
  const h=harness(),old=deferred();h.behavior.board=()=>old.promise;h.configure();await h.clock.advance();
  h.configure({workspace:'other'});assert.equal(h.calls[0].signal.aborted,true);
  h.behavior.board=q=>board(q);old.reject(Object.assign(Error('old403'),{status:403}));await flush();await h.clock.advance(1000);
  assert.equal(h.controller.getState().board.scope.workspace_id,'other');assert.equal(h.controller.getState().status,'ready');
  h.controller.holdOrder(true);h.behavior.board=q=>board(q,{revision:'b2',entry_revision:'e2',columns:{active:slice(),needs_you:slice([entry('work','e2','other')]),results:slice()}});
  h.controller.refresh();await h.clock.advance(1000);assert.equal(h.controller.getState().hasPendingUpdate,true);
  assert.equal(h.controller.getState().board.columns.needs_you.items.length,0);
  h.controller.apply();assert.equal(h.controller.getState().board.columns.needs_you.items.length,1);h.controller.dispose();
});

test('duplicate cross-column cards or foreign column pages fail closed rather than masquerading as counts',async()=>{
  const h=harness();h.behavior.board=q=>board(q,{columns:{active:slice([entry()]),needs_you:slice([entry()]),results:slice()}});
  h.configure();await h.clock.advance();assert.equal(h.controller.getState().board,null);assert.equal(h.controller.getState().status,'error');h.controller.dispose();
});
