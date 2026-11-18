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
const count=value=>({value,total_is_exact:value!==null});
const operational=(patch={})=>({version:1,connection:'connected',activity:'idle',blocking:'none',freshness:'current',as_of:'2026-11-17T12:00:00Z',state_since:null,reason_code:null,
  pending_actions:count(0),pending_by_kind:Object.fromEntries(['question','approval','decision','verification'].map(k=>[k,count(0)])),
  pending_request_ids:[],has_more_pending_requests:false,pending_requests_cursor:null,running_sessions:count(0),blocked_sessions:count(0),awaiting_native_confirmation:false,...patch});
const operationalSummary=Object.fromEntries(['connected','working','idle','queued','unconfirmed','disconnected','blocked_harnesses','pending_actions','visible_notifications','resume_confirmations'].map(k=>[k,count(0)]));
const semantics={version:1,scope:'turn',evidence:'canonical',execution_outcome:'succeeded',task_state:'open',verification:'not_applicable',verification_evidence_ref:null,cleanup:'complete',content_state:'available',historical:false,semantic_revision:'s1'};
const v2card=(patch={})=>({...card(),sessions:[],sessions_total:0,has_more_sessions:false,sessions_cursor:null,operational_status:operational(),placement_reason:'normal_monitoring',resume_confirmation_refs:[],...patch});
const v2board=(q,patch={})=>board(q,{presentation_version:2,operational_summary:operationalSummary,columns:{active:slice([v2card()]),needs_you:slice([{...request(),blocks_session:false,action_kind:'question'}]),results:slice([{...delivery(),completion_evidence:'canonical',delivery_semantics:semantics,result:{id:'report',delivery_semantics:semantics}}])},...patch});
function harness(){
  const clock=new Clock(),calls=[];let active=0,peak=0;
  const behavior={harnessBoard:q=>board(q),harnessBoardColumn:(name,q)=>({...board(q),partition:'harness_board_column',column:name,...slice([card('card2')],{total:2})}),
    harnessChildren:(id,q)=>({...board(q),partition:'harness_children',card_id:id,...slice([child('work2')],{total:2})}),
    harnessUnlinked:q=>({...board(q),partition:'harness_unlinked',...slice([child('unlinked2')],{total:2})}),
    harnessSessions:(id,q)=>({...v2board(q),partition:'harness_sessions',card_id:id,...slice()}),
    harnessRequests:(id,q)=>({...v2board(q),partition:'harness_requests',card_id:id,...slice()})};
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

test('identical paused polling and observation timestamps do not create pending changes or block detail paging',async()=>{
  const h=harness();h.configure();await h.clock.advance();h.controller.pause(true);
  h.behavior.harnessBoard=q=>board(q,{generated_at:'2026-11-17T12:01:00Z',event_cursor:2,
    columns:{active:slice([{...card(),children:[{...child(),as_of:'2026-11-17T12:01:00Z'}]}],{total:2,has_more:true,next_cursor:'active-cursor'}),needs_you:slice([request()]),results:slice([delivery()])}});
  // Start with as_of already present; only its observation value changes.
  h.controller.pause(false);h.controller.refresh();await h.clock.advance(1000);h.controller.pause(true);
  h.behavior.harnessBoard=q=>board(q,{generated_at:'2026-11-17T12:02:00Z',event_cursor:3,
    columns:{active:slice([{...card(),children:[{...child(),as_of:'2026-11-17T12:02:00Z'}]}],{total:2,has_more:true,next_cursor:'active-cursor'}),needs_you:slice([request()]),results:slice([delivery()])}});
  await h.clock.advance(30000);assert.equal(h.controller.getState().hasPendingUpdate,false);
  h.controller.loadHarnessChildren('card');await h.clock.advance(1000);
  assert.equal(h.calls.filter(c=>c.name==='harnessChildren').length,1);assert.equal(h.peak(),1);h.controller.dispose();
});

test('a paused real transition is retained, but normal board changes are notices rather than errors',async()=>{
  const h=harness();h.configure();await h.clock.advance();h.controller.pause(true);
  h.behavior.harnessBoard=q=>board(q,{revision:'b2',entry_revision:'e2',unlinked:slice(),columns:{active:slice([{...card('card','e2'),activity_state:'working'}]),needs_you:slice(),results:slice()}});
  h.controller.refresh();await h.clock.advance(1000);
  assert.equal(h.controller.getState().hasPendingUpdate,true);assert.equal(h.controller.getState().harnessBoard.revision,'b1');
  assert.equal(h.controller.getState().error,null);assert.match(h.controller.getState().notice,/revalidated/);
  h.controller.apply();assert.equal(h.controller.getState().harnessBoard.revision,'b2');h.controller.dispose();
});

test('presentation negotiation is generation-bound and v1 omits the query parameter',async()=>{
  const h=harness();h.configure();await h.clock.advance();const first=h.controller.getState().generation;
  assert.equal('presentation_version' in h.calls[0].args[0],false);
  h.behavior.harnessBoard=v2board;h.configure({presentationVersion:2});assert.equal(h.controller.getState().harnessBoard,null);await h.clock.advance(1000);
  assert.ok(h.controller.getState().generation>first);assert.equal(h.calls.at(-1).args[0].presentation_version,2);h.controller.dispose();
});

test('v2 admits awaiting confirmation without inventing blocks_harness and requires scoped semantic fields',async()=>{
  const awaiting=v2card({blocks_harness:false,activity_state:'awaiting_confirmation',placement_reason:'awaiting_native_confirmation',
    operational_status:operational({activity:'awaiting_confirmation',awaiting_native_confirmation:true}),
    resume_confirmation_refs:[{request_id:'q',decision_id:'d',operation_id:'op',session_id:'session',stream_epoch:'epoch'}]});
  const h=harness();h.behavior.harnessBoard=q=>v2board(q,{columns:{active:slice(),needs_you:slice([awaiting]),results:slice()}});
  h.configure({presentationVersion:2});await h.clock.advance();assert.equal(h.controller.getState().status,'ready');
  assert.equal(h.controller.getState().harnessBoard.columns.needs_you.items[0].blocks_harness,false);h.controller.dispose();
  for(const patch of [{resume_confirmation_refs:[]},{operational_status:undefined},{placement_reason:'normal_monitoring'},
    {operational_status:operational({awaiting_native_confirmation:false})}]){
    const x=harness();x.behavior.harnessBoard=q=>v2board(q,{columns:{active:slice(),needs_you:slice([{...awaiting,...patch}]),results:slice()}});
    x.configure({presentationVersion:2});await x.clock.advance();assert.equal(x.controller.getState().harnessBoard,null);x.controller.dispose();
  }
  for(const patch of [{presentation_version:undefined},{operational_summary:undefined},
    {columns:{active:slice([v2card()]),needs_you:slice(),results:slice([{...delivery(),completion_evidence:'canonical',delivery_semantics:semantics,result:{id:'report',delivery_semantics:{...semantics,semantic_revision:'other'}}}])}}]){
    const x=harness();x.behavior.harnessBoard=q=>v2board(q,patch);x.configure({presentationVersion:2});await x.clock.advance();
    assert.equal(x.controller.getState().harnessBoard,null);x.controller.dispose();
  }
});

test('pending board presentation does not block current contextual reads and pages',async()=>{
  const h=harness();h.configure();await h.clock.advance();h.controller.pause(true);
  const fresh=q=>board(q,{revision:'b2',entry_revision:'e2',unlinked:slice(),columns:{active:slice([card('card','e2')]),needs_you:slice(),results:slice()}});
  h.behavior.harnessBoard=fresh;h.controller.refresh();await h.clock.advance(1000);
  h.behavior.harnessChildren=(id,q)=>({...fresh(q),partition:'harness_children',card_id:id,
    ...slice([child(q.cursor?'third':'fresh','e2')],{total:2,has_more:!q.cursor,next_cursor:q.cursor?null:'fresh-cursor'})});
  h.controller.loadHarnessChildren('card');await h.clock.advance(1000);
  assert.equal(h.calls.at(-1).name,'harnessChildren');assert.equal('cursor'in h.calls.at(-1).args[1],false);
  assert.deepEqual(h.controller.getState().harnessChildren.card.items.map(x=>x.id),['fresh']);
  h.controller.loadHarnessChildren('card');await h.clock.advance(1000);
  assert.equal(h.calls.at(-1).args[1].cursor,'fresh-cursor');
  assert.deepEqual(h.controller.getState().harnessChildren.card.items.map(x=>x.id),['fresh','third']);
  assert.equal(h.controller.getState().harnessBoard.revision,'b1');assert.equal(h.controller.getState().hasPendingUpdate,true);
  assert.equal(h.peak(),1);h.controller.dispose();
});

test('a context read queued during background polling survives and uses the current scope',async()=>{
  const h=harness();h.configure();await h.clock.advance();const wait=deferred();
  h.behavior.harnessBoard=()=>wait.promise;await h.clock.advance(15000);
  h.controller.refreshHarnessChildren('card');assert.equal(h.peak(),1);
  wait.resolve(board({workspace_id:'ws'}));await flush();await h.clock.advance(1000);
  assert.equal(h.calls.at(-1).name,'harnessChildren');assert.equal('cursor'in h.calls.at(-1).args[1],false);
  assert.equal(h.peak(),1);h.controller.dispose();
});

test('409 rereads the context first page in place and does not append old rows or replay forever',async()=>{
  const h=harness();h.configure();await h.clock.advance();h.controller.pause(true);let calls=0;
  h.behavior.harnessChildren=(id,q)=>{calls++;if(q.cursor)throw Object.assign(Error('changed'),{status:409});
    return {...board(q),partition:'harness_children',card_id:id,...slice([child('current')])};};
  h.controller.loadHarnessChildren('card');await h.clock.advance(3000);
  assert.equal(calls,2);assert.deepEqual(h.controller.getState().harnessChildren.card.items.map(x=>x.id),['current']);
  assert.equal(h.controller.getState().error,null);assert.equal(h.peak(),1);h.controller.dispose();
});

test('403 clears paused detail caches and queued reads immediately',async()=>{
  const h=harness();h.configure();await h.clock.advance();h.controller.pause(true);
  h.behavior.harnessChildren=()=>{throw Object.assign(Error('denied'),{status:403});};
  h.controller.refreshHarnessChildren('card');await h.clock.advance(1000);
  assert.equal(h.controller.getState().status,'forbidden');assert.equal(h.controller.getState().harnessBoard,null);
  assert.deepEqual(h.controller.getState().harnessChildren,{});const count=h.calls.length;
  h.controller.refreshHarnessChildren('card');await h.clock.advance(30000);assert.equal(h.calls.length,count);h.controller.dispose();
});

test('binding sessions and action relations use the same queue and retain exact parents',async()=>{
  const h=harness();h.behavior.harnessBoard=v2board;
  h.behavior.harnessSessions=(id,q)=>({...v2board(q),partition:'harness_sessions',card_id:id,
    ...slice([{server_id:'server',executor_id:'executor',workspace_id:'ws',session_id:q.cursor?'second':'first',lifecycle_state:'READY'}],
      {total:2,has_more:!q.cursor,next_cursor:q.cursor?null:'sessions-2'})});
  h.behavior.harnessRequests=(id,q)=>({...v2board(q),partition:'harness_requests',card_id:id,...slice([{...request(),blocks_session:true,action_kind:'question'}])});
  h.configure({presentationVersion:2});await h.clock.advance();h.controller.pause(true);
  h.controller.loadHarnessSessions('card');await h.clock.advance(1000);h.controller.loadHarnessSessions('card');await h.clock.advance(1000);
  assert.deepEqual(h.controller.getState().harnessSessions.card.items.map(s=>s.session_id),['first','second']);
  assert.equal(h.calls.at(-1).args[1].cursor,'sessions-2');assert.equal(h.calls.at(-1).args[1].presentation_version,2);
  h.controller.loadHarnessRequests('card');await h.clock.advance(1000);
  assert.equal(h.controller.getState().harnessRequests.card.items[0].request.attention_id,'question');
  assert.equal(h.controller.getState().paused,true);assert.equal(h.peak(),1);h.controller.dispose();
});

test('operational observation time is not a delta, but freshness and transition facts are',async()=>{
  const h=harness();h.behavior.harnessBoard=v2board;h.configure({presentationVersion:2});await h.clock.advance();h.controller.pause(true);
  h.behavior.harnessBoard=q=>v2board(q,{columns:{...v2board(q).columns,active:slice([v2card({operational_status:operational({as_of:'2026-11-17T12:01:00Z'})})])}});
  h.controller.refresh();await h.clock.advance(1000);assert.equal(h.controller.getState().hasPendingUpdate,false);
  h.behavior.harnessBoard=q=>v2board(q,{columns:{...v2board(q).columns,active:slice([v2card({operational_status:operational({activity:'unknown',freshness:'stale',reason_code:'EXPIRED'})})])}});
  h.controller.refresh();await h.clock.advance(1000);assert.equal(h.controller.getState().hasPendingUpdate,true);h.controller.dispose();
});

test('session relation rejects foreign identity and auth failure clears every new relation cache',async()=>{
  for(const forbidden of [false,true]){
    const h=harness();h.behavior.harnessBoard=v2board;h.configure({presentationVersion:2});await h.clock.advance();
    h.behavior.harnessSessions=(id,q)=>{if(forbidden)throw Object.assign(Error('denied'),{status:403});
      return {...v2board(q),partition:'harness_sessions',card_id:id,...slice([{server_id:'server',executor_id:'foreign',workspace_id:'ws',session_id:'same'}])};};
    h.controller.loadHarnessSessions('card');await h.clock.advance(1000);
    assert.deepEqual(h.controller.getState().harnessSessions,{});
    if(forbidden){assert.equal(h.controller.getState().status,'forbidden');assert.equal(h.controller.getState().harnessBoard,null);}
    h.controller.dispose();
  }
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

test('current v2 partial coverage does not age current harness proof; legacy mapping stays compatible',async()=>{
  for(const version of [1,2]){
    const h=harness();
    h.behavior.harnessBoard=q=>version===2?v2board(q,{status:'partial'}):board(q,{status:'partial'});
    h.configure({presentationVersion:version});await h.clock.advance();
    const state=h.controller.getState();
    assert.equal(state.status,version===2?'ready':'stale');
    assert.equal(state.harnessBoard.status,'partial');
    assert.equal(state.harnessBoard.source_status.external,'disabled');
    if(version===2)assert.equal(state.harnessBoard.columns.active.items[0].operational_status.freshness,'current');
    h.controller.dispose();
  }
});

test('v2 partial snapshots keep unknown proof and real refresh failure stale',async()=>{
  const h=harness();
  h.behavior.harnessBoard=q=>v2board(q,{status:'partial',columns:{...v2board(q).columns,
    active:slice([v2card({operational_status:operational({connection:'unknown',activity:'unknown',blocking:'unknown',freshness:'unavailable'})})])}});
  h.configure({presentationVersion:2});await h.clock.advance();
  assert.equal(h.controller.getState().status,'ready');
  assert.equal(h.controller.getState().harnessBoard.columns.active.items[0].operational_status.freshness,'unavailable');
  h.behavior.harnessBoard=()=>{throw Error('offline');};h.controller.refresh();await h.clock.advance(1000);
  assert.equal(h.controller.getState().status,'stale');assert.ok(h.controller.getState().error);
  assert.ok(h.controller.getState().staleSections.length>0);
  h.controller.pause(false);assert.equal(h.controller.getState().status,'stale');
  assert.ok(h.controller.getState().error);h.controller.dispose();
});

test('held v2 partial updates still age the displayed snapshot and preserve current data for apply',async()=>{
  const h=harness();h.behavior.harnessBoard=q=>v2board(q,{status:'partial'});
  h.configure({presentationVersion:2});await h.clock.advance();h.controller.pause(true);
  h.behavior.harnessBoard=q=>v2board(q,{status:'partial',revision:'b2'});
  h.controller.refresh();await h.clock.advance(1000);
  assert.equal(h.controller.getState().hasPendingUpdate,true);
  assert.equal(h.controller.getState().harnessBoard.revision,'b1');
  h.controller.pause(false);
  assert.equal(h.controller.getState().harnessBoard.revision,'b2');
  assert.equal(h.controller.getState().status,'ready');h.controller.dispose();
});
