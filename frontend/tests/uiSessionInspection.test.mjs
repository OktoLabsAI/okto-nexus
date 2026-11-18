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
const render=props=>renderToStaticMarkup(React.createElement(SessionExecutionPanel,props));

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
