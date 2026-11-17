import assert from 'node:assert/strict';
import test from 'node:test';
import {moduleURL,Clock,deferred,flush} from './homeR1Support.mjs';
const {HomeController}=await import(await moduleURL('homeController.ts'));
const slice=(items=[],patch={})=>({items,total:items.length,total_is_exact:true,has_more:false,next_cursor:null,...patch});
const child=(id='work',revision='e1')=>({id,group_id:'original-group',entry_revision:revision,shared_reference:false,workspace_id:'ws',target:null,
  sessions:[],attention_refs:[],result_refs:[]});
const connection={server_id:'server',executor_id:'executor',binding_id:'binding',workspace_id:'ws',workspace_binding_id:'wxb',agent_id:'agent',harness_id:'codex_app_server',agent_label:'Collaborator',host_label:'Host'};
const card=(id='card',revision='e1')=>({kind:'harness',id,group_id:id,context_state:'registered',blocks_harness:false,blocking_request_ids:[],blocking_requests:[],activity_state:'registered',reminder_snoozed:false,reconnect_available:false,reconnect_reason:'Unavailable',connection,
  target:{kind:'connection',server_id:'server',executor_id:'executor',workspace_id:'ws',binding_id:'binding',agent_id:'agent'},
  children:[child('work',revision)],children_total:2,has_more_children:true,children_cursor:'children-cursor',events_preview:[],events_total:0,events_summary:{attention:0,results:0,work:0,sessions:0,external:0},summary:{}});
const request=(id='request',revision='e1')=>({kind:'request',id,request:{attention_id:'question',source_revision:'q1'},entry:child('work',revision),harness_refs:[{card_id:'card',connection}],blocks_harness:null,notification_visible:true});
const delivery=(id='delivery',revision='e1')=>({kind:'delivery',id,result:{id:'report'},entry:child('work',revision),harness_refs:[{card_id:'card',connection}],completion_evidence:'reported'});
const board=(query={},patch={})=>({version:1,partition:'harness_board',server_id:'server',scope:{workspace_id:query.workspace_id??null,quick:'all',include_recent_results:false},
  status:'ready',revision:'b1',entry_revision:'e1',snapshot_id:'b1',generated_at:'2026-11-17T12:00:00Z',as_of:null,next_refresh_at:null,event_cursor:1,event_low_watermark:1,
  source_status:{work:'ready',results:'ready',attention:'ready',connections:'ready',sessions:'ready',correlations:'ready',external:'disabled'},coverage:{result_tracking:'ready'},summary:{},
  server_attention:{status:'ready',items:[],total:0,total_is_exact:true,has_more:false},unlinked:slice([child('unlinked')],{total:2,has_more:true,next_cursor:'unlinked-cursor'}),
  columns:{active:slice([card()],{total:2,has_more:true,next_cursor:'active-cursor'}),needs_you:slice([request()]),results:slice([delivery()])},...patch});
function harness(){
  const clock=new Clock(),calls=[];let active=0,peak=0;
  const behavior={harnessBoard:q=>board(q),harnessBoardColumn:(name,q)=>({...board(q),partition:'harness_board_column',column:name,...slice([card('card2')],{total:2})}),
    harnessChildren:(id,q)=>({...board(q),partition:'harness_children',card_id:id,...slice([child('work2')],{total:2})}),
    harnessUnlinked:q=>({...board(q),partition:'harness_unlinked',...slice([child('unlinked2')],{total:2})})};
  const api=Object.fromEntries(Object.keys(behavior).map(name=>[name,async(...args)=>{const signal=args.at(-1);calls.push({name,args:args.slice(0,-1),signal});active++;peak=Math.max(active,peak);
    try{return await behavior[name](...args.slice(0,-1));}finally{active--;}}]));
  const controller=new HomeController({api,now:()=>clock.now,setTimeout:clock.set,clearTimeout:clock.clear});
  const configure=patch=>controller.configure({family:'harness',workspace:'ws',identityKey:'operator',visible:true,...patch});
  return {clock,calls,behavior,controller,configure,peak:()=>peak};
}
test('one Server board admits Active harness plus distinct request/delivery of the same connection, without source merging',async()=>{
  const h=harness();h.configure();await h.clock.advance();
  const root=h.controller.getState().harnessBoard;assert.ok(root);assert.equal(root.columns.active.items[0].kind,'harness');
  assert.equal(root.columns.needs_you.items[0].blocks_harness,null);assert.equal(root.columns.results.items[0].completion_evidence,'reported');
  assert.deepEqual(h.calls.map(call=>call.name),['harnessBoard']);assert.equal('quick' in h.calls[0].args[0],false);
  h.controller.loadBoardColumn('active');await h.clock.advance(1000);assert.equal(h.controller.getState().harnessBoard.columns.active.items.length,2);assert.equal(h.peak(),1);h.controller.dispose();
});
test('explicit contextual paging uses the same queue while display is paused, without publishing a newer root',async()=>{
  const h=harness();h.configure();await h.clock.advance();h.controller.pause(true);
  h.controller.loadHarnessChildren('card');await h.clock.advance(1000);
  assert.deepEqual(h.controller.getState().harnessChildren.card.items.map(item=>item.id),['work','work2']);
  assert.equal(h.controller.getState().harnessBoard.revision,'b1');assert.equal(h.controller.getState().paused,true);
  h.controller.loadHarnessChildren(null);await h.clock.advance(1000);assert.deepEqual(h.controller.getState().harnessUnlinked.items.map(item=>item.id),['unlinked','unlinked2']);
  assert.equal(h.peak(),1);h.controller.dispose();
});
test('a contextual409 invalidates every root/page cursor and resnapshots all columns before any old append',async()=>{
  const h=harness();h.configure();await h.clock.advance();h.controller.loadHarnessChildren('card');await h.clock.advance(1000);
  h.behavior.harnessUnlinked=()=>{throw Object.assign(Error('changed'),{status:409});};
  h.behavior.harnessBoard=q=>board(q,{revision:'b2',entry_revision:'e2',unlinked:slice(),columns:{active:slice(),needs_you:slice([{...card('card','e2'),blocks_harness:true,blocking_request_ids:['question']}]),results:slice([delivery('delivery','e2')])}});
  h.controller.loadHarnessChildren(null);await h.clock.advance(1000);
  assert.deepEqual(h.controller.getState().harnessChildren,{});assert.equal(h.controller.getState().harnessBoard.columns.active.next_cursor,null);
  h.controller.loadBoardColumn('active');await h.clock.advance(1000);
  const state=h.controller.getState();assert.equal(state.harnessBoard.revision,'b2');assert.equal(state.harnessBoard.columns.active.items.length,0);
  assert.equal(state.harnessBoard.columns.needs_you.items[0].blocks_harness,true);assert.deepEqual(h.calls.map(call=>call.name),['harnessBoard','harnessChildren','harnessUnlinked','harnessBoard']);h.controller.dispose();
});
test('new global revision clears all loaded children and unlinked pages; queued cursors and oldscope403 cannot survive',async()=>{
  const h=harness();h.configure();await h.clock.advance();h.controller.loadHarnessChildren('card');await h.clock.advance(1000);
  h.controller.loadHarnessChildren(null);await h.clock.advance(1000);h.controller.loadBoardColumn('active');
  h.behavior.harnessBoard=q=>board(q,{revision:'b2',entry_revision:'e2',unlinked:slice(),columns:{active:slice([card('card','e2')]),needs_you:slice(),results:slice()}});
  h.controller.invalidate({type:'native.changed',event_id:2});await h.clock.advance(1000);
  assert.deepEqual(h.controller.getState().harnessChildren,{});assert.equal(h.controller.getState().harnessUnlinked,null);
  assert.equal(h.calls.some(call=>call.name==='harnessBoardColumn'),false);h.controller.dispose();
  const next=harness(),old=deferred();next.behavior.harnessBoard=()=>old.promise;next.configure();await next.clock.advance();next.configure({identityKey:'new-operator'});
  assert.equal(next.calls[0].signal.aborted,true);next.behavior.harnessBoard=q=>board(q);old.reject(Object.assign(Error('old denied'),{status:403}));await flush();await next.clock.advance(1000);
  assert.equal(next.controller.getState().status,'ready');next.controller.dispose();
});
test('foreign parents, duplicate item IDs and forbidden column variants fail closed',async()=>{
  for(const columns of [{active:slice([request()]),needs_you:slice(),results:slice()},
    {active:slice([card(),card()]),needs_you:slice(),results:slice()},
    {active:slice([{...card(),connection:{...connection,workspace_binding_id:null}}]),needs_you:slice(),results:slice()}]){
    const h=harness();h.behavior.harnessBoard=q=>board(q,{columns});h.configure();await h.clock.advance();assert.equal(h.controller.getState().harnessBoard,null);assert.equal(h.controller.getState().status,'error');h.controller.dispose();
  }
  const h=harness();h.configure();await h.clock.advance();h.behavior.harnessChildren=(id,q)=>({...board(q),partition:'harness_children',card_id:'foreign',...slice([child('work2')],{total:2})});
  h.controller.loadHarnessChildren('card');await h.clock.advance(1000);assert.deepEqual(h.controller.getState().harnessChildren,{});h.controller.dispose();
});
test('request and reported delivery with unknown origin do not invalidate the board or fabricate a harness',async()=>{
  const h=harness();
  const unknownRequest={...request(),harness_refs:[],entry:{...child(),target:null}};
  const unknownDelivery={...delivery(),result:null,report:{attention_id:'external-completion',source_revision:'report1'},harness_refs:[],entry:{...child(),target:null}};
  h.behavior.harnessBoard=q=>board(q,{columns:{active:slice(),needs_you:slice([unknownRequest]),results:slice([unknownDelivery])}});
  h.configure();await h.clock.advance();
  const state=h.controller.getState();assert.equal(state.status,'ready');assert.ok(state.harnessBoard);
  assert.equal(state.harnessBoard.columns.active.items.length,0);
  assert.deepEqual(state.harnessBoard.columns.needs_you.items[0].harness_refs,[]);
  assert.deepEqual(state.harnessBoard.columns.results.items[0].harness_refs,[]);
  assert.equal(state.harnessBoard.columns.results.items[0].completion_evidence,'reported');
  assert.equal(state.harnessBoard.columns.results.items[0].result,null);
  assert.equal(state.harnessBoard.columns.needs_you.items[0].entry.target,null);
  assert.deepEqual(h.calls.map(call=>call.name),['harnessBoard']);h.controller.dispose();
});
test('nonempty origin references remain fully scoped and complete',async()=>{
  for(const reference of [{card_id:'card',connection:{...connection,workspace_id:'foreign'}},
    {card_id:'card',connection:{...connection,workspace_binding_id:null}},{card_id:'',connection}]){
    const h=harness();h.behavior.harnessBoard=q=>board(q,{columns:{active:slice(),needs_you:slice([{...request(),harness_refs:[reference]}]),results:slice()}});
    h.configure();await h.clock.advance();assert.equal(h.controller.getState().harnessBoard,null);assert.equal(h.controller.getState().status,'error');h.controller.dispose();
  }
});
test('QC public metadata association changes revision and resets pages without renaming the canonical card or adapter',async()=>{
  const h=harness();h.configure();await h.clock.advance();h.controller.loadHarnessChildren('card');await h.clock.advance(1000);
  const before=h.controller.getState().harnessBoard.columns.active.items[0];
  h.behavior.harnessBoard=q=>board(q,{revision:'b2',entry_revision:'e2',unlinked:slice(),columns:{active:slice([{...card('card','e2'),connection:{...connection,connect_id:'reviewer'}}]),needs_you:slice(),results:slice()}});
  h.controller.refresh();await h.clock.advance(1000);const state=h.controller.getState(),after=state.harnessBoard.columns.active.items[0];
  assert.equal(after.id,before.id);assert.equal(after.group_id,before.group_id);assert.equal(after.connection.connect_id,'reviewer');
  assert.equal(after.connection.harness_id,before.connection.harness_id);assert.equal(after.connection.binding_id,before.connection.binding_id);
  assert.deepEqual(state.harnessChildren,{});assert.equal(h.calls.every(call=>call.name.startsWith('harness')),true);h.controller.dispose();
  for(const connect_id of ['Reviewer','../bad','a'.repeat(65),1]){
    const invalid=harness();invalid.behavior.harnessBoard=q=>board(q,{columns:{active:slice([{...card(),connection:{...connection,connect_id}}]),needs_you:slice(),results:slice()}});
    invalid.configure();await invalid.clock.advance();assert.equal(invalid.controller.getState().harnessBoard,null);invalid.controller.dispose();
  }
});
