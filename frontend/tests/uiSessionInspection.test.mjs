import assert from 'node:assert/strict';
import {existsSync,readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import test from 'node:test';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import ts from 'typescript';
import {moduleURL,deferred} from './homeR1Support.mjs';
const {readHomeSessionInspection}=await import(await moduleURL('homeSessionInspection.ts'));
const {homeInspectionTarget}=await import(await moduleURL('homeNavigation.ts'));

const context={server_id:'server',executor_id:'executor',workspace_id:'workspace',session_id:'exact-session',binding_id:'admitted-binding',workspace_binding_id:'admitted-wxb',agent_id:'agent',lifecycle_state:'CLOSED'};
const session=patch=>({scope:{...context,session_owner_generation:1,authorization_revision:1,configuration_revision:1,binding_revision:1,credential_epoch:1},
  lifecycle_state:'CLOSED',lease_state:'CLOSED',control_available:false,durable_release_pending:false,...patch});
const require=createRequire(import.meta.url),modules=new Map();
function load(url){
  const filename=fileURLToPath(url);if(modules.has(filename))return modules.get(filename).exports;
  const module={exports:{}};modules.set(filename,module);
  const code=ts.transpileModule(readFileSync(filename,'utf8'),{fileName:filename,compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText;
  const localRequire=name=>{
    if(name.endsWith('.css'))return {};
    if(!name.startsWith('.'))return require(name);
    const path=['.ts','.tsx','/index.ts'].map(ext=>new URL(name+ext,url)).find(p=>existsSync(p));assert.ok(path,name);return load(path);
  };
  new Function('require','module','exports',code)(localRequire,module,module.exports);return module.exports;
}
const {SessionExecutionPanel}=load(new URL('../src/components/SessionExecutionPanel.tsx',import.meta.url));
const {assertConversationPage,assertConversationPosition,applyConversationUpdates,liveTurnAnnouncement,
  interactionKey,inputIntentStorageKey,readInputIntent,clearInputIntents}=
  load(new URL('../src/sessionConversation.ts',import.meta.url));
const {interruptStatus,canDismissInterrupt,interruptStorageKey,clearInterruptIntents}=load(new URL('../src/sessionInterrupt.ts',import.meta.url));
const {assertSteerPreview,steerReceiptOutcome,steerStorageKey,readSteerReference,clearSteerReferences}=
  load(new URL('../src/sessionSteer.ts',import.meta.url));
const render=props=>renderToStaticMarkup(React.createElement(SessionExecutionPanel,props));

test('an interrupt receipt stays distinct from proof that the target stopped',()=>{
  const receipt={executor_stage:'SUCCEEDED',admission_state:'RESOLVED_TERMINAL',possible_effect:true,error:null,
    interrupt:{target_status:'unconfirmed',queue_paused:true,pending_count:2}};
  assert.match(interruptStatus(receipt),/delivered.*Waiting/);
  assert.equal(canDismissInterrupt(receipt),false);
  const confirmed={...receipt,interrupt:{...receipt.interrupt,target_status:'interrupted'}};
  assert.equal(interruptStatus(confirmed),'Turn interrupted.');
  assert.equal(canDismissInterrupt(confirmed),true);
  const refused={...receipt,error:{code:'CONTROL_REFUSED'},possible_effect:false,
    interrupt:{...receipt.interrupt,target_status:'running'}};
  assert.match(interruptStatus(refused),/refused.*still running/);
  assert.equal(canDismissInterrupt(refused),true);
});

test('interrupt recovery references stay isolated by full scope and are cleared with the login',()=>{
  const exact={...context,session_owner_generation:3};
  const exactKey=interruptStorageKey(exact);
  const nextKey=interruptStorageKey({...exact,session_owner_generation:4});
  const otherKey=interruptStorageKey({...exact,executor_id:'other'});
  assert.equal(new Set([exactKey,nextKey,otherKey]).size,3);
  const items=new Map([[exactKey,'intent-a'],['unrelated-ui-preference','keep'],[otherKey,'intent-b']]);
  clearInterruptIntents({get length(){return items.size;},key:index=>[...items.keys()][index],removeItem:key=>items.delete(key)});
  assert.deepEqual([...items], [['unrelated-ui-preference','keep']]);
});

test('next-turn recovery restores only a valid intent in the exact owner scope',()=>{
  const scope={...context,session_owner_generation:3};
  const exactKey=inputIntentStorageKey(scope);
  const otherKey=inputIntentStorageKey({...scope,session_id:'different-session'});
  const nextOwnerKey=inputIntentStorageKey({...scope,session_owner_generation:4});
  const intent='ui_12345678-1234-1234-1234-123456789abc';
  const items=new Map([[exactKey,intent],[otherKey,'invalid-draft-text'],['preference','keep']]);
  const storage={get length(){return items.size;},key:index=>[...items.keys()][index],getItem:key=>items.get(key),
    removeItem:key=>items.delete(key)};
  assert.equal(readInputIntent(storage,exactKey),intent);
  assert.equal(readInputIntent(storage,nextOwnerKey),null);
  assert.equal(readInputIntent(storage,otherKey),null);
  clearInputIntents(storage);
  assert.deepEqual([...items], [['preference','keep']]);
});

test('reorientation reviews freeze the supported effect, owner generation and queued input',()=>{
  const scope={...context,session_owner_generation:3};
  const control={effect:'same_turn',effect_revision:'effect',capability_revision:'capability',
    queue_revision:4,target:{kind:'native_turn',turn_id:'native-turn'}};
  const preview={scope,session_owner_generation:3,control,queued_input:{input_id:'queued-a',input_revision:1}};
  const source={kind:'queue',inputId:'queued-a'};
  assert.doesNotThrow(()=>assertSteerPreview(preview,scope,source));
  assert.throws(()=>assertSteerPreview({...preview,session_owner_generation:4},scope,source));
  assert.throws(()=>assertSteerPreview({...preview,control:{...control,effect:'interrupt_replace'}},scope,source));
  assert.throws(()=>assertSteerPreview(preview,scope,{kind:'queue',inputId:'queued-b'}));
  const pi={...control,effect:'next_boundary',target:{kind:'observed_run',run_ref:'prun_'+'a'.repeat(32)}};
  assert.doesNotThrow(()=>assertSteerPreview({...preview,control:pi},scope,source));
  assert.throws(()=>assertSteerPreview({...preview,control:{...pi,effect:'same_turn'}},scope,source));
  const claude={...control,effect:'interrupt_then_send',target:{kind:'claude_operation',operation_id:'op_'+'a'.repeat(32)}};
  assert.doesNotThrow(()=>assertSteerPreview({...preview,control:claude},scope,source));
  assert.throws(()=>assertSteerPreview({...preview,control:{...claude,target:control.target}},scope,source));
});

test('a reorientation receipt never conflates queue dispatch, submission and native acceptance',()=>{
  const scope={...context,session_owner_generation:3};
  const source={kind:'queue',inputId:'queued-a'};
  const receipt={scope,session_owner_generation:3,operation_id:'op-x',input_id:'queued-a',status:'DISPATCHING',
    possible_effect:false,reorientation:true,steer_submitted:false};
  assert.equal(steerReceiptOutcome(receipt,scope,source),'dispatching');
  assert.equal(steerReceiptOutcome({...receipt,steer_submitted:true},scope,source),'submitted');
  assert.equal(steerReceiptOutcome({...receipt,status:'ACCEPTED_NATIVE'},scope,source),'accepted');
  assert.equal(steerReceiptOutcome({...receipt,status:'REFUSED_BEFORE_SEND'},scope,source),'refused');
  assert.equal(steerReceiptOutcome({...receipt,possible_effect:true,status:'REFUSED_BEFORE_SEND'},scope,source),'uncertain');
  assert.equal(steerReceiptOutcome({...receipt,reorientation:false,status:'QUEUED'},scope,source),'uncertain');
  assert.equal(steerReceiptOutcome({...receipt,reorientation:false},scope,source),'original-changed');
  assert.throws(()=>steerReceiptOutcome({...receipt,input_id:'different'},scope,source));
  const pi={...source,awaitBoundary:true};
  const submitted={...receipt,possible_effect:true,steer_submitted:true};
  assert.equal(steerReceiptOutcome(submitted,scope,pi),'boundary-unconfirmed');
  for (const boundary of ['awaiting_boundary','applied','discarded']) {
    assert.equal(steerReceiptOutcome({...submitted,steer_boundary:boundary},scope,pi),boundary);
  }
  assert.throws(()=>steerReceiptOutcome({...receipt,steer_boundary:'applied'},scope,pi));
  const claude={...source,awaitCompound:true};
  assert.equal(steerReceiptOutcome(submitted,scope,claude),'uncertain');
  const interrupted={...submitted,steer_compound:{interruption:'confirmed',replacement:'pending'}};
  assert.equal(steerReceiptOutcome(interrupted,scope,claude),'compound-pending');
  assert.equal(steerReceiptOutcome({...interrupted,status:'DELIVERY_UNKNOWN',
    steer_compound:{interruption:'submitted',replacement:'not_sent'}},scope,claude),'compound-pending');
  const replacement={...interrupted,steer_compound:{interruption:'confirmed',replacement:'submitted'}};
  assert.equal(steerReceiptOutcome(replacement,scope,claude),'compound-pending');
  assert.equal(steerReceiptOutcome({...replacement,status:'ACCEPTED_NATIVE'},scope,claude),'accepted');
  const uncertainWrite={...replacement,steer_compound:{interruption:'confirmed',replacement:'write_unknown'}};
  assert.equal(steerReceiptOutcome({...uncertainWrite,status:'DELIVERY_UNKNOWN'},scope,claude),'compound-pending');
  assert.equal(steerReceiptOutcome({...uncertainWrite,status:'ACCEPTED_NATIVE'},scope,claude),'accepted');
  assert.throws(()=>steerReceiptOutcome({...replacement,
    steer_compound:{interruption:'submitted',replacement:'submitted'}},scope,claude));
});

test('reorientation stores only the exact recovery reference and clears its keys on logout',()=>{
  const scope={...context,session_owner_generation:3};
  const key=steerStorageKey(scope);
  const other=steerStorageKey({...scope,session_owner_generation:4});
  const items=new Map([[key,JSON.stringify({kind:'queue',inputId:'queued-a',text:'ignored'})],[other,'invalid'],['keep','setting']]);
  const storage={get length(){return items.size;},key:index=>[...items.keys()][index],getItem:key=>items.get(key),
    removeItem:key=>items.delete(key)};
  assert.deepEqual(readSteerReference(storage,key),{kind:'queue',inputId:'queued-a'});
  items.set(key,JSON.stringify({kind:'queue',inputId:'queued-a',text:'ignored',awaitCompound:true}));
  assert.deepEqual(readSteerReference(storage,key),{kind:'queue',inputId:'queued-a',awaitCompound:true});
  assert.equal(readSteerReference(storage,other),null);
  clearSteerReferences(storage);
  assert.deepEqual([...items.keys()],['keep']);
});

test('passive session inspection sends exact session/executor and verifies all seven admitted scope fields',async()=>{
  const calls=[],client={session:async(...args)=>{calls.push(args);return session();}};
  const value=await readHomeSessionInspection(client,context);
  assert.equal(value.scope.session_id,context.session_id);
  assert.equal(calls[0][0],context.session_id);assert.equal(calls[0][2],context.executor_id);
  for(const key of ['server_id','executor_id','workspace_id','session_id','binding_id','workspace_binding_id','agent_id'])
    await assert.rejects(readHomeSessionInspection({session:async()=>session({scope:{...context,[key]:'foreign'}})},context));
});

test('late cancelled reads and authorization failures never produce a replacement session',async()=>{
  const pending=deferred(),abort=new AbortController();
  const read=readHomeSessionInspection({session:()=>pending.promise},context,abort.signal);
  abort.abort();pending.resolve(session());await assert.rejects(read,{name:'AbortError'});
  for(const status of [401,403,404]) {
    let calls=0;
    await assert.rejects(readHomeSessionInspection({session:async()=>{calls++;throw Object.assign(new Error('denied'),{status});}},context));
    assert.equal(calls,1);
  }
});

test('actual embedded output body is read-only history without a nested dialog or terminal maximizer',()=>{
  const markup=render({session:session(),embedded:true});
  assert.match(markup,/Read only/);assert.match(markup,/Runtime session history/);
  assert.doesNotMatch(markup,/exact-session|Copy command|<dialog|Maximize terminal|<textarea|Submit|Interrupt|Continue session/);
  assert.match(markup,/aria-pressed="true"[^>]*>History/);
});
test('an eligible embedded session offers an exact shell-safe terminal command only in its disclosure',()=>{
  const active=session({scope:{...session().scope,session_id:'ses_exact_abc'},lifecycle_state:'READY',lease_state:'ACTIVE',control_available:true});
  const markup=render({session:active,embedded:true});
  assert.match(markup,/<details[^>]*><summary[^>]*>Open this session in a terminal/);
  assert.match(markup,/okto-nexus work chat --session-id ses_exact_abc/);
  assert.match(markup,/saved profile for this connection/);
  assert.match(markup,/Copy command/);
  assert.equal((markup.match(/ses_exact_abc/g)||[]).length,1);
  for (const patch of [{control_available:false},{durable_release_pending:true},{lifecycle_state:'CLOSED'},
    {scope:{...active.scope,session_id:'ses_x; unsafe'}}]) {
    assert.doesNotMatch(render({session:{...active,...patch},embedded:true}),/Copy command|okto-nexus work chat/);
  }
});

test('continuation is offered only for a session that can still accept it',()=>{
  const onContinue=()=>{};
  const live=session({lifecycle_state:'READY',lease_state:'ACTIVE',control_available:true});
  assert.match(render({session:live,embedded:true,interactive:true,onContinue}),/button[^>]*>Continue this exact session/);
  const unavailable=[
    {lifecycle_state:'CLOSED'},
    {lifecycle_state:'FAILED'},
    {lifecycle_state:'CLOSING'},
    {lifecycle_state:'DRAINING'},
    {lease_state:'CLOSED'},
    {durable_release_pending:true},
    {control_available:false},
  ];
  for(const patch of unavailable){
    const markup=render({session:{...live,...patch},embedded:true,interactive:true,onContinue});
    assert.doesNotMatch(markup,/Continue this exact session/);
    assert.match(markup,/Conversation/);
  }
});

test('only the read-only session body excludes observation controls from captured draft edits',()=>{
  const markup=render({session:session(),embedded:true});
  assert.match(markup,/^<section aria-label="Session execution output" data-modal-passive="true"/);
  assert.match(markup,/<input type="checkbox"[^>]*\/> Auto-scroll/);
  const {RuntimeOperations}=load(new URL('../src/components/RuntimeOperations.tsx',import.meta.url));
  const form=renderToStaticMarkup(React.createElement(RuntimeOperations,{agentId:'agent',binding:{binding_id:'binding',agent_id:'agent'},canStart:false}));
  assert.match(form,/<textarea aria-label="Runtime message"/);
  assert.doesNotMatch(form,/data-modal-passive/,'canonical runtime form remains outside the passive viewer boundary');
});

test('standalone wrapper body retains terminal maximizer while exact-session target selects passive inspector',()=>{
  assert.match(render({session:session(),harness:'codex_app_server',host:'Recorded host'}),/Maximize terminal/);
  const target={kind:'session',server_id:context.server_id,executor_id:context.executor_id,workspace_id:context.workspace_id,session_id:context.session_id};
  const resolved={version:1,available:true,source_revision:'revision',target,agent_id:context.agent_id,session_context:context};
  assert.deepEqual(homeInspectionTarget(resolved),{kind:'session',context});
  assert.equal(homeInspectionTarget({...resolved,session_context:{...context,workspace_id:'foreign'}}).kind,'unavailable');
});

test('the interactive Home body opens conversation and keeps existing controls in technical activity',()=>{
  const markup=render({session:session(),embedded:true,interactive:true,technicalControls:React.createElement('button',null,'Older runtime actions')});
  assert.match(markup,/aria-pressed="true"[^>]*>Conversation/);
  assert.match(markup,/Technical activity/);
  assert.doesNotMatch(markup,/Older runtime actions|Runtime session history/);
});

test('the Home console puts one event terminal above the exact-session composer',()=>{
  const active=session({lifecycle_state:'READY',lease_state:'ACTIVE',control_available:true});
  const markup=render({session:active,embedded:true,interactive:true,consoleView:true,harness:'pi_rpc'});
  assert.match(markup,/aria-label="Live runtime events"[\s\S]*aria-label="Session input"[\s\S]*<textarea/);
  assert.match(markup,/Pi · terminal/);
  assert.doesNotMatch(markup,/Session view|Technical activity|Conversation messages|Maximize terminal|Read only|Open this session in a terminal/);
  assert.equal((markup.match(/<textarea/g)||[]).length,1);
});

test('the Home console keeps historical output and requires a known owner for the composer',()=>{
  const closed=render({session:session(),embedded:true,interactive:true,consoleView:true});
  assert.match(closed,/Recorded runtime events/);
  assert.doesNotMatch(closed,/<textarea/);
  const noOwner=session({scope:{...session().scope,session_owner_generation:undefined},lifecycle_state:'READY'});
  const active=render({session:noOwner,embedded:true,interactive:true,consoleView:true});
  assert.match(active,/Live runtime events/);
  assert.doesNotMatch(active,/<textarea/);
});

test('Activity detail can render only the conversation for an exact session',()=>{
  const markup=render({session:session(),embedded:true,interactive:true,conversationOnly:true});
  assert.match(markup,/aria-label="Session conversation view"[\s\S]*aria-label="Conversation messages"/);
  assert.doesNotMatch(markup,/Session view|Technical activity|Runtime session history|Maximize terminal|<textarea/);
});

test('conversation cursor pages cannot cross scope, owner generation or stream',()=>{
  const scope=session().scope;
  const page={scope,stream_epoch:'epoch',next_after_sequence:2,committed_contiguous:3,has_more:true,updates:[]};
  assert.doesNotThrow(()=>assertConversationPage(page,scope,0,'epoch'));
  const replaced={...scope,session_owner_generation:2};
  assert.notEqual(interactionKey(scope),interactionKey(replaced));
  assert.throws(()=>assertConversationPage({...page,scope:replaced},scope,0,'epoch'));
  assert.throws(()=>assertConversationPage(page,scope,2,'epoch'));
  assert.throws(()=>assertConversationPage(page,scope,0,'foreign-epoch'));
});

test('conversation uses verified incoming message text while preserving ordinary native input',()=>{
  const scope={...context,session_owner_generation:1};
  const nativeScope={kind:'native_session',session_id:'native'};
  const text='NEXUS DELIVERY: internal context';
  const incoming={update_id:'u1',message_id:'m1',sequence:1,role:'user',change:'replace',text,
    text_truncated:true,origin:nativeScope,delivery_message:{text:'Check shipment',text_truncated:false}};
  const literal={...incoming,update_id:'u2',message_id:'m2',sequence:2,delivery_message:undefined,
    text_truncated:false};
  const page={scope,stream_epoch:'epoch',next_after_sequence:2,committed_contiguous:2,updates:[incoming,literal]};
  assert.doesNotThrow(()=>assertConversationPage(page,scope,0,'epoch'));
  assert.throws(()=>assertConversationPage({...page,updates:[{...incoming,role:'assistant'}]},scope,0,'epoch'));
  const messages=applyConversationUpdates(new Map(),page.updates);
  assert.deepEqual([...messages.values()],[
    {role:'user',text:'Check shipment',truncated:false,incoming:true},
    {role:'user',text,truncated:false},
  ]);
});

test('conversation cursor reports its next missing committed sequence without offering a later page',()=>{
  const scope=session().scope;
  const page={scope,stream_epoch:'epoch',next_after_sequence:7,committed_contiguous:20,
    has_more:false,history_gap:8,updates:[]};
  assert.doesNotThrow(()=>assertConversationPage(page,scope,7,'epoch'));
  assert.throws(()=>assertConversationPage({...page,history_gap:9},scope,7,'epoch'));
  assert.throws(()=>assertConversationPage({...page,committed_contiguous:7},scope,7,'epoch'));
  assert.throws(()=>assertConversationPage({...page,has_more:true},scope,6,'epoch'));
});

test('conversation announces new verified turn outcomes as one message per page',()=>{
  const scope=session().scope;
  const page={scope,stream_epoch:'epoch',next_after_sequence:12,committed_contiguous:12,
    has_more:false,updates:[],turn_outcomes:[{sequence:8,outcome:'success'},{sequence:11,outcome:'interrupted'}]};
  assert.doesNotThrow(()=>assertConversationPage(page,scope,7,'epoch'));
  assert.throws(()=>assertConversationPage({...page,turn_outcomes:[...page.turn_outcomes,page.turn_outcomes[1]]},scope,7,'epoch'));
  assert.throws(()=>assertConversationPage({...page,turn_outcomes:[{sequence:13,outcome:'success'}]},scope,7,'epoch'));
  assert.equal(liveTurnAnnouncement(page,12),null);
  assert.deepEqual(liveTurnAnnouncement(page,7),{sequence:11,text:'2 turns ended.'});
  assert.deepEqual(liveTurnAnnouncement(page,8),{sequence:11,text:'Turn interrupted.'});
  assert.equal(liveTurnAnnouncement({...page,turn_outcomes:undefined},7),null);
});

test('consecutive live notices remain distinguishable to assistive technology',()=>{
  const page={turn_outcomes:[{sequence:8,outcome:'success'},{sequence:11,outcome:'success'}]};
  const first=liveTurnAnnouncement(page,0);
  assert.deepEqual(first,{sequence:11,text:'2 turns ended.'});
  const later={turn_outcomes:[{sequence:12,outcome:'success'},{sequence:15,outcome:'success'}]};
  assert.deepEqual(liveTurnAnnouncement(later,11,first.text),{sequence:15,text:'2 more turns ended.'});
  assert.deepEqual(liveTurnAnnouncement(later,12,'Turn finished.'),{sequence:15,text:'Another turn finished.'});
  assert.deepEqual(liveTurnAnnouncement(later,12,'Another turn finished.'),{sequence:15,text:'Turn finished.'});
  assert.equal(liveTurnAnnouncement(later,15,'Turn finished.'),null);
});

test('conversation reconciles deltas and snapshots by message identity with stable prior rows',()=>{
  const initial=new Map();
  const part={message_id:'message',update_id:'delta',change:'append',role:'assistant',text:'part',text_truncated:false};
  const first=applyConversationUpdates(initial,[part,part]);
  assert.equal(initial.size,0);
  assert.equal(first.get('message').text,'part');
  const next=applyConversationUpdates(first,[{...part,update_id:'snapshot',change:'replace',text:'complete'},
    {...part,message_id:'other',update_id:'other',change:'replace',text:'complete'}]);
  assert.deepEqual([...next.keys()],['message','other']);
  assert.equal(next.get('message').text,'complete');
  assert.equal(first.get('message').text,'part');
});

test('conversation preserves explicit subagent origin and rejects incomplete attribution',()=>{
  const scope=session().scope;
  const main={message_id:'main',update_id:'main',sequence:1,change:'replace',role:'assistant',text:'same',text_truncated:false};
  const child={...main,message_id:'child',update_id:'child',sequence:2,
    origin:{kind:'subagent',session_id:'native',parent_tool_use_id:'toolu_child'}};
  const page={scope,stream_epoch:'epoch',next_after_sequence:2,committed_contiguous:2,has_more:false,updates:[main,child]};
  assert.doesNotThrow(()=>assertConversationPage(page,scope,0,'epoch'));
  assert.throws(()=>assertConversationPage({...page,updates:[{...child,origin:{...child.origin,parent_tool_use_id:''}}]},scope,0,'epoch'));
  const messages=applyConversationUpdates(new Map(),page.updates);
  assert.equal(messages.get('main').subagent,undefined);
  assert.equal(messages.get('child').subagent,true);
});

test('conversation position notifications cannot move another owner or accept an invalid cursor',()=>{
  const scope=session().scope;
  const position={version:1,scope,stream_epoch:'epoch',committed_contiguous:4,gap_pending:false};
  assert.doesNotThrow(()=>assertConversationPosition(position,scope));
  assert.throws(()=>assertConversationPosition({...position,committed_contiguous:-1},scope));
  assert.throws(()=>assertConversationPosition({...position,stream_epoch:null},scope));
  assert.throws(()=>assertConversationPosition({...position,scope:{...scope,session_owner_generation:2}},scope));
});

test('a missing suffix does not splice in later fragments before the completed snapshot',()=>{
  const delta={message_id:'message',update_id:'first',change:'append',role:'assistant',text:'prefix',text_truncated:true};
  const omitted=applyConversationUpdates(new Map(),[delta,{...delta,update_id:'later',text:'later suffix',text_truncated:false}]);
  assert.deepEqual(omitted.get('message'),{role:'assistant',text:'prefix',truncated:true});
  const complete=applyConversationUpdates(omitted,[{...delta,update_id:'final',change:'replace',
    text:'prefix restored interval and later suffix',text_truncated:false}]);
  assert.deepEqual(complete.get('message'),{role:'assistant',text:'prefix restored interval and later suffix',truncated:false});
});
