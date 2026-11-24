import assert from 'node:assert/strict';
import {existsSync,readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import test from 'node:test';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import ts from 'typescript';
import {moduleURL,deferred} from './homeR1Support.mjs';

const navigation=await moduleURL('attentionNavigation.ts');
const continuation=await moduleURL('components/home/continuation.ts');
const exact=await import(await moduleURL('components/home/exactRuntimeOperations.ts',{
  '../../attentionNavigation':navigation,'./continuation':continuation,
}));
const {readExactExecutionContext,readExactSessionContext,assertExactRequest,assertExactResolution,revalidateExactContext,
  exactScopeKey,exactStorageIdentity,mayDiscardExactRequest,pendingExactRequests,clearExactRuntimeRequests}=exact;
const scope={server_id:'server',agent_id:'agent',executor_id:'executor',binding_id:'binding',workspace_id:'workspace',workspace_binding_id:'wxb',session_id:'session'};
const target={kind:'execution',agent:'agent',executor:'executor',operation:'exact-operation',session:'session',workspace:'workspace'};
const operation=patch=>({operation_id:'exact-operation',scope:{...scope},action:'turn.submit',admission_state:'ACCEPTED',executor_stage:'RUNNING',
  possible_effect:true,retry_safe:false,error:null,follow_up_operation_ids:[],result:{output_text:'retained-output-marker',output_truncated:0},...patch});
const session=patch=>({scope:{...scope},lifecycle_state:'READY',lease_state:'ACTIVE',control_available:true,durable_release_pending:false,...patch});
const binding=patch=>({binding_id:'binding',agent_id:'agent',executor_id:'executor',workspace_id:'workspace',workspace_binding_id:'wxb',adapter_id:'codex_app_server',state:'APPROVED',...patch});
const request=(intent='turn.submit')=>({client_intent_id:'original-request',agent_id:'agent',binding_id:'binding',workspace_binding_id:'wxb',session_id:'session',intent,
  ...(intent==='turn.interrupt'?{target:{kind:'current_run',expected_turn_id:null}}:{})});
const resolution=req=>({scope:{...scope},session_id:'session',client_intent_id:req.client_intent_id,semantic_intent:{action:req.intent},operation_id:'new-action'});

test('execution reader uses only the exact operation, session, binding and current Server',async()=>{
  const calls=[];
  const value=await readExactExecutionContext({agentRuntimeExecution:async(...args)=>{calls.push(['operation',...args.slice(0,3)]);return operation();}},
    {me:async()=>{calls.push(['me']);return {server_id:'server'};},session:async(id,signal,executor)=>{calls.push(['session',id,executor]);return session();},
      binding:async id=>{calls.push(['binding',id]);return binding();}},target);
  assert.equal(value.operation.operation_id,'exact-operation');
  assert.deepEqual(calls,[['operation','agent','exact-operation','executor'],['me'],['session','session','executor'],['binding','binding']]);
});

test('a session without an operation reads only its exact scope and never selects a sibling',async()=>{
  const calls=[];
  const client={me:async()=>{calls.push('me');return {server_id:'server'};},
    session:async(id,signal,executor)=>{calls.push([id,executor]);return session();},binding:async id=>{calls.push(id);return binding();}};
  const result=await readExactSessionContext(client,scope);assert.equal(result.session.scope.session_id,'session');
  assert.deepEqual(calls,['me',['session','executor'],'binding']);
  for(const field of Object.keys(scope))await assert.rejects(readExactSessionContext({...client,
    session:async()=>session({scope:{...scope,[field]:'sibling'}})},scope));
});

test('all seven session dimensions and every binding dimension refuse scope drift without replacement',async()=>{
  for(const field of Object.keys(scope))await assert.rejects(readExactExecutionContext({agentRuntimeExecution:async()=>operation()},
    {me:async()=>({server_id:'server'}),session:async()=>session({scope:{...scope,[field]:'foreign'}}),binding:async()=>binding()},target));
  for(const field of ['binding_id','agent_id','executor_id','workspace_id','workspace_binding_id'])
    await assert.rejects(readExactExecutionContext({agentRuntimeExecution:async()=>operation()},
      {me:async()=>({server_id:'server'}),session:async()=>session(),binding:async()=>binding({[field]:'foreign'})},target));
  await assert.rejects(readExactExecutionContext({agentRuntimeExecution:async()=>operation()},
    {me:async()=>({server_id:'other-server'}),session:async()=>session(),binding:async()=>binding()},target));
});

test('cancellation discards late exact reads before a binding lookup',async()=>{
  const wait=deferred(),abort=new AbortController();let reads=0;
  const value=readExactExecutionContext({agentRuntimeExecution:async()=>operation()},
    {me:async()=>({server_id:'server'}),session:()=>wait.promise,binding:async()=>{reads++;return binding();}},target,abort.signal);
  await Promise.resolve();await Promise.resolve();abort.abort();wait.resolve(session());
  await assert.rejects(value,{name:'AbortError'});assert.equal(reads,0);
});

test('each exact intent has a fixed session and interrupt target; start, steer and new-session payloads are refused',()=>{
  for(const intent of ['turn.submit','turn.interrupt','runtime.close'])assert.doesNotThrow(()=>assertExactRequest(request(intent),{scope}));
  for(const patch of [{intent:'runtime.start'},{intent:'turn.steer'},{new_session:true},{new_session:false},{session_id:'sibling'},{agent_id:'other'},{binding_id:'other'},{workspace_binding_id:'other'}])
    assert.throws(()=>assertExactRequest({...request(),...patch},{scope}));
  assert.throws(()=>assertExactRequest({...request('turn.interrupt'),target:{kind:'native_turn_id',expected_turn_id:'guessed-from-operation'}},{scope}));
  assert.throws(()=>assertExactRequest(request('runtime.close'),{scope},['turn.submit']));
});

test('a receipt or resolution for another intent or any other scope cannot authorize submission',()=>{
  const req=request();assert.doesNotThrow(()=>assertExactResolution(resolution(req),req,{scope}));
  for(const field of Object.keys(scope))assert.throws(()=>assertExactResolution({...resolution(req),scope:{...scope,[field]:'sibling'}},req,{scope}));
  assert.throws(()=>assertExactResolution({...resolution(req),semantic_intent:{action:'runtime.close'}},req,{scope}));
  assert.throws(()=>assertExactResolution({...resolution(req),client_intent_id:'another-request'},req,{scope}));
});

test('all actions revalidate the exact session and approved binding, without an inventory read or grant issuance',async()=>{
  const calls=[],client={session:async(id,signal,executor)=>{calls.push(['session',id,executor]);return session();},binding:async id=>{calls.push(['binding',id]);return binding();}};
  for(const intent of ['turn.submit','turn.interrupt','runtime.close'])await revalidateExactContext(client,{scope},intent);
  assert.equal(calls.length,6);assert.ok(calls.every(call=>call[1]===(call[0]==='session'?'session':'binding')));
  await assert.rejects(revalidateExactContext({...client,session:async()=>session({control_available:false})},{scope},'turn.submit'));
  await assert.rejects(revalidateExactContext({...client,binding:async()=>binding({state:'DISABLED'})},{scope},'runtime.close'));
  await assert.rejects(revalidateExactContext(client,{scope},'runtime.start'));
});

test('unknown review/admission cannot discard or create replacement while a confirmed refusal can',()=>{
  assert.equal(mayDiscardExactRequest({submissionAttempted:false,reviewAttempted:true,resolution:null},false),false);
  assert.equal(mayDiscardExactRequest({submissionAttempted:false,resolution:null},false),false);
  assert.equal(mayDiscardExactRequest({submissionAttempted:true,reviewAttempted:true,resolution:resolution(request())},false),false);
  assert.equal(mayDiscardExactRequest({submissionAttempted:false,reviewAttempted:true,resolution:null,reviewError:'confirmed validation refusal'},false),true);
  assert.equal(mayDiscardExactRequest({submissionAttempted:true,resolution:resolution(request())},true),true);
});

test('seven-field cache and intent partitions still find another original unknown action',()=>{
  const key=intent=>JSON.stringify(exactStorageIdentity(scope,intent));
  const current={request:request('turn.interrupt'),resolution:null,submissionAttempted:true,reviewAttempted:true};
  const storage=new Map([[key('turn.interrupt'),JSON.stringify(current)]]);
  assert.deepEqual(pendingExactRequests({getItem:key=>storage.get(key)??null},key,{scope}),[current]);
  assert.notEqual(key('turn.interrupt'),key('runtime.close'));
  for(const field of Object.keys(scope))assert.notEqual(exactScopeKey(scope),exactScopeKey({...scope,[field]:'sibling'}));
  storage.set(key('runtime.close'),'{');assert.throws(()=>pendingExactRequests({getItem:key=>storage.get(key)??null},key,{scope}));
});

test('logout redacts attempted requests while retaining recovery fences across relogin',()=>{
  const key=intent=>`okto-nexus:r4-runtime:${JSON.stringify(['server','operator','agent','binding',...exactStorageIdentity(scope,intent),'wxb'])}`;
  const advanced='okto-nexus:r4-runtime:'+JSON.stringify(['server','operator','home-exact','binding','wxb']);
  const req={...request('turn.interrupt'),text:'protected-message'};
  const original={request:req,resolution:{...resolution(req),private_response:'protected-response'},submissionAttempted:true,reviewAttempted:true};
  const map=new Map([[key('turn.interrupt'),JSON.stringify(original)],[advanced,'advanced'],['other','unrelated'],
    [key('turn.submit'),JSON.stringify({request:{...request(),text:'draft-message'},resolution:null,reviewAttempted:false,submissionAttempted:false})]]);
  const storage={get length(){return map.size;},key:i=>[...map.keys()][i],removeItem:key=>map.delete(key),getItem:key=>map.get(key)??null,setItem:(key,value)=>map.set(key,value)};
  clearExactRuntimeRequests(storage);clearExactRuntimeRequests(storage);
  assert.equal(map.has(key('turn.submit')),false);assert.equal(map.get(advanced),'advanced');assert.equal(map.get('other'),'unrelated');
  const retained=map.get(key('turn.interrupt'));assert.doesNotMatch(retained,/protected-message|protected-response|draft-message/);
  const [pending]=pendingExactRequests(storage,key,{scope});
  assert.equal(pending.request.client_intent_id,'original-request');assert.equal(pending.request.intent,'turn.interrupt');assert.equal(pending.quarantined,true);
  assert.equal(pending.recoveryRef.operation_id,'new-action');assert.equal(pending.resolution,null);
  assert.equal(mayDiscardExactRequest(pending,false),false);
  assert.equal(mayDiscardExactRequest({...pending,resolution:resolution(req),recoveryConfirmed:true},false),false);
  assert.equal(mayDiscardExactRequest({...pending,resolution:resolution(req),recoveryConfirmed:true},true),true);
  assert.equal(mayDiscardExactRequest({...pending,submissionAttempted:false,recoveryConfirmed:false},false),false);
  assert.equal(mayDiscardExactRequest({...pending,submissionAttempted:false,recoveryConfirmed:true},false),true);
});

const require=createRequire(import.meta.url),modules=new Map();
function load(url){
  const filename=fileURLToPath(url);if(modules.has(filename))return modules.get(filename).exports;
  const module={exports:{}};modules.set(filename,module);
  const code=ts.transpileModule(readFileSync(filename,'utf8'),{fileName:filename,compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText;
  const localRequire=name=>{if(name.endsWith('.css'))return {};if(!name.startsWith('.'))return require(name);
    const path=['.ts','.tsx','/index.ts'].map(ext=>new URL(name+ext,url)).find(p=>existsSync(p));assert.ok(path,name);return load(path);};
  new Function('require','module','exports',code)(localRequire,module,module.exports);return module.exports;
}
const {RuntimeOperations}=load(new URL('../src/components/RuntimeOperations.tsx',import.meta.url));
const {HomeExecutionDetails,ExactSessionControls}=load(new URL('../src/components/home/HomeExecutionInspection.tsx',import.meta.url));
const html=(component,props)=>renderToStaticMarkup(React.createElement(component,props));

test('actual contextual controls exclude start, manual session/native-turn, other-agent and automatic selection',()=>{
  const markup=html(RuntimeOperations,{agentId:'agent',binding:binding(),canStart:false,exactContext:{scope},suppressOutput:true});
  assert.match(markup,/Continue this exact session/);assert.match(markup,/Interrupt the current run in this exact session/);assert.match(markup,/Close this exact session/);
  assert.match(markup,/data-modal-passive/);
  assert.doesNotMatch(markup,/Runtime session ID|Native turn ID|Session selection|Create a new session|Start or reuse|Steer a turn|Running instances|Last 10/);
});

test('actual exact inspector suppresses duplicate output for entry panels; legacy standalone retains one viewer',()=>{
  const context={operation:operation(),session:session(),binding:binding()};
  const suppressed=html(HomeExecutionDetails,{context,suppressOutput:true});
  assert.doesNotMatch(suppressed,/exact-operation|Session execution output|retained-output-marker|Running instances|Last 10/);
  const standalone=html(HomeExecutionDetails,{context,suppressOutput:false});
  assert.equal((standalone.match(/aria-label="Session execution output"/g)||[]).length,1);
  assert.match(standalone,/retained-output-marker/);assert.doesNotMatch(standalone,/<dialog|Maximize terminal|Running instances|Last 10/);
});

test('a selected result remains visible alongside the shared conversation without another transcript',()=>{
  const context={operation:operation(),session:session(),binding:binding()};
  const markup=html(HomeExecutionDetails,{context,suppressOutput:true,showRetainedResult:true});
  assert.match(markup,/aria-label="Retained execution result"[\s\S]*retained-output-marker/);
  assert.doesNotMatch(markup,/Session execution output/);
});

test('uncertain original execution exposes no new actions, while Advanced retains its existing full selector',()=>{
  const markup=html(HomeExecutionDetails,{context:{operation:operation({executor_stage:'OUTCOME_UNKNOWN'}),session:session(),binding:binding()}});
  assert.match(markup,/recorded outcome is unknown/);assert.doesNotMatch(markup,/Review runtime action|Runtime action/);
  assert.match(markup,/Reference for troubleshooting[\s\S]*exact-operation/);
  const advanced=html(RuntimeOperations,{agentId:'agent',binding:binding(),canStart:true});
  assert.match(advanced,/Start or reuse a runtime/);assert.match(advanced,/Runtime session ID|Session selection/);
});

test('session-only controls use the same exact whitelist; closed or draining cannot create a new session',()=>{
  const available=html(ExactSessionControls,{session:session(),binding:binding()});
  assert.match(available,/Continue this exact session/);assert.match(available,/Close this exact session/);
  assert.doesNotMatch(available,/Session selection|Start or reuse|Runtime session ID/);
  for(const lifecycle_state of ['CLOSED','FAILED','CLOSING','DRAINING']){
    const markup=html(ExactSessionControls,{session:session({lifecycle_state}),binding:binding()});
    assert.doesNotMatch(markup,/Runtime action|Review runtime action/);assert.match(markup,/separate explicit intention/);
  }
});
