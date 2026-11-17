import assert from 'node:assert/strict';
import test from 'node:test';
import {moduleURL,Clock,deferred,flush} from 'file:///D:/Projetos/Techridy/okto_labs_okto_nexus/frontend/tests/homeR1Support.mjs';
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

const observations=[];
test('characterization: identical paused polling prevents contextual pagination',async()=>{
 const h=harness();h.configure();await h.clock.advance();
 const before=JSON.stringify(h.controller.getState().harnessBoard);
 h.controller.pause(true);
 for(let cycle=1;cycle<=2;cycle++){
  await h.clock.advance(15000);
  const state=h.controller.getState();
  h.controller.loadHarnessChildren('card');await h.clock.advance(1000);
  observations.push({cycle,clock:h.clock.now,paused:state.paused,pending:state.hasPendingUpdate,
   sameVisibleSnapshot:JSON.stringify(state.harnessBoard)===before,status:state.status,error:state.error,
   staleSections:state.staleSections,boardReads:h.calls.filter(c=>c.name==='harnessBoard').length,
   childReads:h.calls.filter(c=>c.name==='harnessChildren').length,peak:h.peak()});
 }
 console.log('REPRODUCTION '+JSON.stringify(observations));
 assert.equal(observations.length,2);
 assert.ok(observations.every(o=>o.pending&&o.sameVisibleSnapshot&&o.childReads===0&&o.status==='ready'&&o.error===null));
 assert.equal(h.calls.filter(c=>c.name==='harnessBoard').length,3);
 assert.equal(h.peak(),1);h.controller.dispose();
});
test('control: paused contextual pagination works before the first identical poll',async()=>{
 const h=harness();h.configure();await h.clock.advance();h.controller.pause(true);
 h.controller.loadHarnessChildren('card');await h.clock.advance(1000);
 assert.equal(h.calls.filter(c=>c.name==='harnessChildren').length,1);
 assert.deepEqual(h.controller.getState().harnessChildren.card.items.map(x=>x.id),['work','work2']);
 assert.equal(h.controller.getState().hasPendingUpdate,false);h.controller.dispose();
});
test('HST-T-F01 desired contract: two identical polls must not block exact detail',async()=>{
 const h=harness();h.configure();await h.clock.advance();h.controller.pause(true);
 await h.clock.advance(30000);
 const pending=h.controller.getState().hasPendingUpdate;
 h.controller.loadHarnessChildren('card');await h.clock.advance(1000);
 const childReads=h.calls.filter(c=>c.name==='harnessChildren').length;h.controller.dispose();
 assert.deepEqual({pending,childReads},{pending:false,childReads:1});
});
