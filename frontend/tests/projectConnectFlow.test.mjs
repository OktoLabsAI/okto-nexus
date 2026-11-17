import assert from 'node:assert/strict';
import {existsSync, readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import test from 'node:test';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import ts from 'typescript';

const require=createRequire(import.meta.url), modules=new Map();
function load(url) {
  const filename=fileURLToPath(url);if(modules.has(filename))return modules.get(filename).exports;
  const module={exports:{}};modules.set(filename,module);
  const code=ts.transpileModule(readFileSync(filename,'utf8'),{fileName:filename,compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText;
  const localRequire=name=>{
    if(name.endsWith('.css'))return {};
    if(!name.startsWith('.'))return require(name);
    const path=['.ts','.tsx','/index.ts'].map(ext=>new URL(name+ext,url)).find(p=>existsSync(p));
    assert.ok(path,name);return load(path);
  };
  new Function('require','module','exports',code)(localRequire,module,module.exports);return module.exports;
}
const {ProjectConnectModel,connectCheckpointKey,connectorDraftCommand}=load(new URL('../src/projectConnectFlowModel.ts',import.meta.url));
const {ProjectConnectFlow}=load(new URL('../src/components/onboarding/ProjectConnectFlow.tsx',import.meta.url));
const {RuntimeManagementError}=load(new URL('../src/runtimeApi.ts',import.meta.url));
const workspace={workspace_id:'logical-project',display_name:'Fixture project'};
const preset={format_version:1,origin:{id:'project-generalist',revision:7},identity:{role:'Project assistant',permissions:{messages:{send_direct:true},limits:{messages_per_minute:43,max_recipients:6}},defaults_hash:'sha256:'+'f'.repeat(64)},
  configuration:{runtime_enabled:true,session_policy:'per_sender',harness_settings:{},tool_access:'ask',authorization:{minutes:17,actions:9,no_expiry:false,unlimited_actions:false}},effects:['A temporary model test may incur provider usage.','Finish saves the reviewed connection.']};
const draft={baseline:{runtime_revision:2,execution_revision:3,defaults_revision:4,binding_revision:null,endpoint_revision:null},runtime_policy:{},agent_creation_defaults:preset.identity,
  native_decision_policy:{value:false,source:'default',editable:true,revision:'a'.repeat(64),can_initialize:true}};
const row=(adapter='codex_app_server',binding='binding-1')=>({server_id:'server-1',binding_id:binding,executor_id:'executor-1',endpoint_id:'endpoint-1',workspace_binding_id:'wxb-1',agent_id:'existing-agent',workspace_id:workspace.workspace_id,
  adapter_id:adapter,binding_revision:1,realization_revision:1,endpoint_revision:1,activation_state:'approved',endpoint_enabled:true,agent_active:true,executor_revoked:false,execution_location:'local',agent_label:'Existing collaborator',workspace_label:workspace.display_name,host_label:'Fixture Server',needs_revalidation:true});
const options={agent_id:'operator-agent',executor_id:'executor-1',inventory_revision:'inventory-1',freshness:'FRESH',adapter_freshness:{codex_app_server:'FRESH',claude_stream:'FRESH'},observations:[],
  options:['codex_app_server','claude_stream'].map(adapter=>({adapter_id:adapter,candidate_ref:'candidate-'+adapter,technical_state:'READY_FOR_RUNTIME',technical_reasons:[],policy_reasons:[],can_configure:true,label:'Observed '+adapter})),
  catalog:{runtimes:[{adapter_id:'codex_app_server',display_name:'Codex',support_status:'managed_supported'},{adapter_id:'claude_stream',display_name:'Claude',support_status:'managed_supported'}]},availability:{platform:'fixture'}};
const clone=value=>JSON.parse(JSON.stringify(value));
function store() {const values=new Map();return {values,getItem:key=>values.get(key)??null,setItem:(key,value)=>values.set(key,value),removeItem:key=>values.delete(key)};}
function fixture(patch={}) {
  const calls=[],storage=store();let count=0,record=null,receipt=null,catalog=[];
  const call=(name,...args)=>calls.push({name,args:clone(args)});
  const api={
    async me(){call('me');return {server_id:'server-1',agent_id:'operator-agent'};},
    async projectPreset(){call('projectPreset');return clone(preset);},
    async connectionWorkspaces(after){call('connectionWorkspaces',after);return {items:[workspace],has_more:false,next_workspace_id:null};},
    async connectionCatalog(filters,cursor){call('connectionCatalog',filters,cursor);return {version:1,server_id:'server-1',scope:clone(filters),revision:'c'.repeat(64),items:clone(catalog),total:catalog.length,total_is_exact:true,has_more:false,next_cursor:null,requires_canonical_revalidation:true,cursor_integrity:'unsigned_scope_checked'};},
    async setupDraft(agent){call('setupDraft',agent);return clone(draft);},
    async executors(agent){call('executors',agent);return [{executor_id:'executor-1',kind:'embedded',label:'Fixture Server'}];},
    async options(agent,executor,workspace){call('options',agent,executor,workspace);return clone(options);},
    async workspacePaths(workspace,executor){call('workspacePaths',workspace,executor);return {items:[{path:'C:/fixture/project'}]};},
    async binding(binding){call('binding',binding);return row('codex_app_server',binding);},
    async checkLocalInstallation(executor,body){call('checkLocalInstallation',executor,body);return {version:'fixture',runtime_authorized:false};},
    async testSetup(body){call('testSetup',body);assert.ok(storage.getItem(connectCheckpointKey('human-1','server-1',workspace.workspace_id)),'request must be retained before Test POST');record={test_id:body.client_intent_id,status:'succeeded',stage:'Connection verified',details:[]};return clone(record);},
    async setupTest(id){call('setupTest',id);if(!record)throw Object.assign(new Error('Test status unavailable'),{code:'CONFLICT'});return clone(record);},
    async finishSetup(body){call('finishSetup',body);assert.ok(storage.getItem(connectCheckpointKey('human-1','server-1',workspace.workspace_id)));const binding={...row(body.configuration.adapter_id,'binding-'+body.agent_id),agent_id:body.agent_id,candidate_ref:body.candidate_ref,inventory_revision:body.inventory_revision,realization_ref:'realization-1',state:'APPROVED'};
      catalog.push(binding);receipt={setup_run_id:body.client_intent_id,request_hash:'sha256:'+'d'.repeat(64),state:'committed',result:{saved:true,agent_created:true,agent_id:body.agent_id,binding}};return clone(receipt.result);},
    async recoverSetup(body){call('recoverSetup',body);if(!receipt)throw Object.assign(new Error('No committed receipt'),{code:'NOT_FOUND'});return clone(receipt);},
    async setupReceipt(id){call('setupReceipt',id);if(!receipt)throw Object.assign(new Error('No committed receipt'),{code:'NOT_FOUND'});return clone(receipt);},
    ...patch,
  };
  const make=identity=>'project-unused';
  const model=(identity='human-1',selected=workspace)=>new ProjectConnectModel(api,storage,identity,selected,prefix=>prefix+(++count));
  return {api,calls,storage,model,setCatalog:value=>{catalog=value;},setTest:value=>{record=value;},setReceipt:value=>{receipt=value;},make};
}
async function reviewed(f,adapter='codex_app_server') {
  const model=f.model();await model.initialize();await model.add();model.selectInstallation('candidate-'+adapter);model.review();return model;
}

test('Add intent enters configuration only after complete canonical reads and never resumes or submits work',async()=>{
  const f=fixture();f.setCatalog([row()]);const model=f.model();
  await model.initialize('add');const state=model.getSnapshot();
  assert.equal(state.phase,'configure');assert.equal(state.workspace.workspace_id,workspace.workspace_id);
  assert.notEqual(state.agentId,'existing-agent');assert.equal(state.request,null);assert.equal(state.retained,false);
  assert.equal(f.calls.filter(c=>c.name==='setupDraft').length,1);
  assert.ok(f.calls.findIndex(c=>c.name==='connectionCatalog')<f.calls.findIndex(c=>c.name==='setupDraft'));
  assert.equal(f.calls.some(c=>['binding','testSetup','finishSetup','recoverSetup','checkLocalInstallation'].includes(c.name)),false);
  const html=renderExistingModel(model,f,{entryMode:'add'});
  assert.match(html,/>Add harness<\/h2>/);assert.doesNotMatch(html,/Existing project connections|Open an existing connection/);
  model.dispose();
});

test('Add intent cannot replace a retained unknown request or start a second concurrent initialization',async()=>{
  const f=fixture({async testSetup(){throw new Error('response lost');}}),first=await reviewed(f);await first.test(true);
  const retained=clone(first.getSnapshot().request);first.dispose();const before=f.calls.length;
  const restored=f.model();await restored.initialize('add');
  assert.equal(restored.getSnapshot().phase,'uncertain');assert.equal(restored.getSnapshot().retained,true);
  assert.deepEqual(restored.getSnapshot().request,retained);
  assert.deepEqual(f.calls.slice(before).map(c=>c.name),['me']);restored.dispose();
  const parallel=fixture();let release,meCalls=0;const gate=new Promise(resolve=>release=resolve),originalMe=parallel.api.me;
  parallel.api.me=async()=>{meCalls++;await gate;return originalMe();};const model=parallel.model();
  const pending=model.initialize('add');await model.initialize('add');assert.equal(meCalls,1);
  assert.equal(parallel.calls.some(c=>c.name==='setupDraft'),false);release();await pending;
  assert.equal(model.getSnapshot().phase,'configure');assert.equal(parallel.calls.filter(c=>c.name==='setupDraft').length,1);model.dispose();
});

test('All projects Add intent requires an explicit authorized project and leaves the classic chooser compatible',async()=>{
  const f=fixture();f.setCatalog([row()]);const all=f.model('human-1',null);await all.initialize('add');
  assert.equal(all.getSnapshot().phase,'choose');assert.equal(f.calls.some(c=>c.name==='setupDraft'),false);
  let html=renderExistingModel(all,f,{entryMode:'add',workspace:null});
  assert.match(html,/<option value=""[^>]*>Choose a project<\/option>/);
  assert.match(html,/<button[^>]*disabled=""[^>]*>Add harness on this Server<\/button>/);
  assert.doesNotMatch(html,/Existing project connections|Open an existing connection|New project on the Server/);
  await all.selectWorkspace(workspace);assert.equal(all.getSnapshot().phase,'choose');
  assert.equal(f.calls.some(c=>c.name==='setupDraft'),false);await all.add();assert.equal(all.getSnapshot().phase,'configure');all.dispose();
  const classic=f.model();await classic.initialize();assert.equal(classic.getSnapshot().phase,'choose');
  html=renderExistingModel(classic,f);assert.match(html,/Existing project connections|Open an existing connection/);assert.match(html,/New project on the Server/);
  const item=classic.getSnapshot().catalog[0];assert.deepEqual(await classic.resume(item),item);
  assert.equal(f.calls.filter(c=>c.name==='binding').length,1);assert.equal(f.calls.some(c=>['testSetup','finishSetup'].includes(c.name)),false);classic.dispose();
});

test('Add intent refuses incomplete catalogs and projects absent from the authorized directory before allocating a draft',async()=>{
  for(const kind of ['catalog','project']){
    const f=fixture();if(kind==='catalog')f.api.connectionCatalog=async()=>{throw new Error('Catalog unavailable');};
    else f.api.connectionWorkspaces=async()=>({items:[],has_more:false,next_workspace_id:null});
    const model=f.model();await model.initialize('add');assert.notEqual(model.getSnapshot().phase,'configure');
    await model.add();assert.notEqual(model.getSnapshot().phase,'configure');
    assert.ok(model.getSnapshot().error);assert.equal(f.calls.some(c=>['setupDraft','testSetup','finishSetup','binding'].includes(c.name)),false);model.dispose();
  }
});

test('selecting a project from All restores its exact retained attempt before exposing Add',async()=>{
  const f=fixture({async testSetup(){throw new Error('response lost');}}),prior=await reviewed(f);await prior.test(true);
  const request=clone(prior.getSnapshot().request);prior.dispose();const before=f.calls.length;
  const all=f.model('human-1',null);await all.initialize('add');assert.equal(all.getSnapshot().phase,'choose');
  await all.selectWorkspace(workspace);assert.equal(all.getSnapshot().phase,'uncertain');assert.equal(all.getSnapshot().retained,true);
  assert.deepEqual(all.getSnapshot().request,request);assert.equal(f.calls.slice(before).some(c=>['setupDraft','binding','testSetup','finishSetup'].includes(c.name)),false);
  await assert.rejects(()=>all.add(),/retained/);assert.equal(f.storage.values.size,1);all.dispose();
});

test('definitive real 422 rejection survives reload and explicit edit archives rather than replaying',async()=>{
  let posts=0;
  const metadata={stage:'connection.test',possible_effect:false,retry_safe:false,operation_id:null,action:''};
  const f=fixture({async testSetup(){posts++;throw new RuntimeManagementError(422,'VALIDATION_ERROR','provider_home is required',undefined,metadata);}});
  let model=await reviewed(f,'claude_stream');await model.test(true);
  const request=clone(model.getSnapshot().request);
  assert.equal(model.getSnapshot().phase,'uncertain');assert.equal(model.getSnapshot().testRejected,true);
  model.dispose();model=f.model();await model.initialize();assert.equal(model.getSnapshot().testRejected,true);
  await model.editRejectedReview();
  assert.equal(model.getSnapshot().phase,'configure');assert.equal(posts,1);
  assert.deepEqual(model.getSnapshot().workspaces,[workspace]);
  assert.deepEqual(model.getSnapshot().workspace,workspace);
  assert.equal(model.getSnapshot().executorLabel,'Fixture Server');
  assert.equal(model.getSnapshot().request,null);assert.equal(model.getSnapshot().retained,false);
  const archive=JSON.parse([...f.storage.values.values()][0]);assert.deepEqual(archive.request,request);
  assert.ok(f.calls.some(c=>c.name==='workspacePaths'));
  assert.equal(f.calls.filter(c=>c.name==='finishSetup').length,0);
  model.review();assert.notEqual(model.getSnapshot().request.client_intent_id,request.client_intent_id);
  assert.equal(posts,1);model.dispose();
});

test('unknown or contradictory errors cannot authorize editing or a replacement test',async()=>{
  const proof={stage:'connection.test',possible_effect:false,retry_safe:false,operation_id:null,action:''};
  const errors=[new Error('response lost'),
    ...[{possible_effect:undefined},{possible_effect:true},{operation_id:'operation-1'},{operation_id:undefined},
      {retry_safe:true},{stage:'connection.finish'},{action:'runtime.open'}].map(change=>new RuntimeManagementError(422,'VALIDATION_ERROR','refused',undefined,{...proof,...change})),
    new RuntimeManagementError(500,'VALIDATION_ERROR','refused',undefined,proof),
    new RuntimeManagementError(422,'NOT_FOUND','refused',undefined,proof)];
  for(const error of errors){
    const f=fixture({async testSetup(){throw error;}}),model=await reviewed(f);await model.test(true);
    assert.equal(model.getSnapshot().testRejected,false);
    await assert.rejects(()=>model.editRejectedReview(),/definitive/);
    assert.ok(f.storage.values.size);assert.equal(f.calls.filter(c=>c.name==='finishSetup').length,0);
    model.dispose();
  }
});

test('definitive rejection still requires same Server, authorized project and absent Finish',async()=>{
  const metadata={stage:'connection.test',possible_effect:false,retry_safe:false,operation_id:null,action:''};
  for(const fence of ['server','workspace','committed','deleted-project','deleted-executor','mismatched-executor','options']){
    const f=fixture({async testSetup(){throw new RuntimeManagementError(422,'VALIDATION_ERROR','refused',undefined,metadata);}});
    const model=await reviewed(f);await model.test(true);
    if(fence==='server')f.api.me=async()=>({server_id:'other',agent_id:'operator-agent'});
    if(fence==='workspace')f.api.workspacePaths=async()=>{throw new Error('Project permission revoked');};
    if(fence==='committed')f.setReceipt({state:'committed'});
    if(fence==='deleted-project')f.api.connectionWorkspaces=async()=>({items:[],has_more:false,next_workspace_id:null});
    if(fence==='deleted-executor')f.api.executors=async()=>[];
    if(fence==='mismatched-executor')f.api.executors=async()=>[{executor_id:'other-host',kind:'embedded',label:'Other host'}];
    if(fence==='options')f.api.options=async()=>{throw new Error('Permission revoked');};
    await model.editRejectedReview();
    assert.equal(model.getSnapshot().phase,'uncertain');assert.equal(model.getSnapshot().retained,true);
    assert.equal(f.storage.values.size,1);model.dispose();
  }
});

test('real canonical preset flags normalize without relaxing portable configuration validation',async()=>{
  for(const authorization of [
    {minutes:60,no_expiry:false,actions:20,unlimited_actions:false},
    {minutes:0,no_expiry:true,actions:0,unlimited_actions:true},
    {minutes:null,no_expiry:true,actions:null,unlimited_actions:true},
  ]) {
    const f=fixture({async projectPreset(){return {...clone(preset),configuration:{...clone(preset.configuration),authorization}};}});
    const model=await reviewed(f);
    assert.equal(model.getSnapshot().phase,'review');
    assert.deepEqual(model.getSnapshot().request.configuration.authorization,
      {minutes:authorization.minutes||null,actions:authorization.actions||null});
    assert.equal(f.calls.some(c=>['testSetup','finishSetup'].includes(c.name)),false);
    model.dispose();
  }
  for(const authorization of [
    {minutes:60,no_expiry:true,actions:20,unlimited_actions:false},
    {minutes:60,no_expiry:false,actions:null,unlimited_actions:false},
    {minutes:60,no_expiry:false,actions:20,unlimited_actions:false,foreign:true},
  ]) {
    const f=fixture({async projectPreset(){return {...clone(preset),configuration:{...clone(preset.configuration),authorization}};}});
    const model=f.model();await model.initialize();await model.add();
    assert.match(model.getSnapshot().error,/authorization/);
    assert.equal(f.calls.some(c=>['testSetup','finishSetup'].includes(c.name)),false);
    model.dispose();
  }
});

test('new identity uses existing operator inventory and reviewed preset; no creation/test before consent',async()=>{
  const f=fixture(),model=await reviewed(f);
  const state=model.getSnapshot(),request=state.request;
  assert.equal(state.phase,'review');assert.equal(request.agent_creation.defaults_hash,preset.identity.defaults_hash);
  assert.deepEqual(request.configuration.authorization,{minutes:17,actions:9});assert.deepEqual(request.project_preset,preset.origin);
  assert.deepEqual(request.native_decision_policy,{expected_revision:'a'.repeat(64),initialize:true});
  assert.equal(request.workspace_id,workspace.workspace_id);assert.equal(request.binding_id,null);assert.equal(request.broadcast_handoff_auto_claim,false);
  assert.ok(f.calls.filter(c=>['options','executors'].includes(c.name)).every(c=>c.args[0]==='operator-agent'));
  assert.equal(f.calls.filter(c=>['testSetup','finishSetup','checkLocalInstallation'].includes(c.name)).length,0);
  await assert.rejects(()=>model.test(false),/consent/);assert.equal(f.storage.values.size,0);
  await model.test(true);assert.equal(model.getSnapshot().phase,'finish');
  assert.throws(()=>model.customize({workspace_root:'C:/other'}),/Recover/);
  await model.finish();assert.equal(model.getSnapshot().phase,'complete');
  assert.equal(f.calls.filter(c=>c.name==='finishSetup').length,1);assert.equal(f.storage.values.size,0);
  model.dispose();
});

test('two reviewed harnesses preserve one canonical project and distinct agent/setup identities',async()=>{
  const f=fixture(),first=await reviewed(f);await first.test(true);await first.finish();
  const second=await reviewed(f,'claude_stream');await second.test(true);await second.finish();
  const requests=f.calls.filter(c=>c.name==='finishSetup').map(c=>c.args[0]);
  assert.deepEqual(requests.map(r=>r.workspace_id),[workspace.workspace_id,workspace.workspace_id]);
  assert.notEqual(requests[0].agent_id,requests[1].agent_id);assert.notEqual(requests[0].client_intent_id,requests[1].client_intent_id);
  assert.deepEqual(requests.map(r=>r.configuration.adapter_id),['codex_app_server','claude_stream']);
  first.dispose();second.dispose();
});

test('catalog pages are complete and Resume only reads exact binding; no grant/session/setup effects',async()=>{
  let pages=0;const rows=Array.from({length:125},(_,i)=>row('codex_app_server','binding-'+i));
  const f=fixture({async connectionCatalog(filters,cursor){pages++;return {version:1,server_id:'server-1',scope:clone(filters),revision:'c'.repeat(64),items:cursor?rows.slice(100):rows.slice(0,100),has_more:!cursor,next_cursor:cursor?null:'next',total:125,total_is_exact:true,requires_canonical_revalidation:true,cursor_integrity:'unsigned_scope_checked'};}});
  const model=f.model();await model.initialize();assert.equal(pages,2);assert.equal(model.getSnapshot().catalog.length,125);
  const selected=model.getSnapshot().catalog[124];assert.deepEqual(await model.resume(selected),selected);
  assert.equal(f.calls.filter(c=>['testSetup','finishSetup','checkLocalInstallation'].includes(c.name)).length,0);
  assert.equal(f.calls.filter(c=>c.name==='binding').length,1);model.dispose();
});

test('lost Test response recovers by same test_id GET, never by another Test or commit recovery POST',async()=>{
  const f=fixture();const original=f.api.testSetup;
  f.api.testSetup=async body=>{await original(body);throw new Error('Lost response');};
  const model=await reviewed(f),id=model.getSnapshot().request.client_intent_id;await model.test(true);
  assert.equal(model.getSnapshot().phase,'uncertain');model.dispose();
  const restored=f.model();await restored.initialize();assert.equal(restored.getSnapshot().phase,'uncertain');
  assert.equal(f.calls.filter(c=>c.name==='testSetup').length,1);
  await restored.recover();assert.equal(restored.getSnapshot().phase,'finish');
  assert.equal(f.calls.filter(c=>c.name==='testSetup').length,1);
  assert.equal(f.calls.filter(c=>c.name==='recoverSetup').length,0);
  assert.equal(f.calls.findLast(c=>c.name==='setupTest').args[0],id);restored.dispose();
});

test('lost Finish response recovers committed receipt without another Test/Finish or identity',async()=>{
  const f=fixture();const original=f.api.finishSetup;
  f.api.finishSetup=async body=>{await original(body);throw new Error('Lost Finish response');};
  const model=await reviewed(f);await model.test(true);await model.finish();assert.equal(model.getSnapshot().phase,'uncertain');model.dispose();
  const restored=f.model();await restored.initialize();await restored.recover();assert.equal(restored.getSnapshot().phase,'complete');
  assert.equal(f.calls.filter(c=>c.name==='testSetup').length,1);assert.equal(f.calls.filter(c=>c.name==='finishSetup').length,1);
  assert.equal(f.calls.filter(c=>c.name==='recoverSetup').length,1);assert.equal(f.storage.values.size,0);restored.dispose();
});

test('unavailable test lookup remains uncertain, immutable and cannot allocate a replacement or retest',async()=>{
  const f=fixture({async testSetup(){throw new Error('Network unavailable');}}),model=await reviewed(f);
  await model.test(true);const request=clone(model.getSnapshot().request);await model.recover();
  assert.equal(model.getSnapshot().phase,'uncertain');assert.deepEqual(model.getSnapshot().request,request);
  assert.throws(()=>model.customize({workspace_root:'C:/replacement'}),/Recover/);
  await assert.rejects(()=>model.test(true),/Review/);assert.equal(f.storage.values.size,1);model.dispose();
});

test('identity/server/project checkpoint fences prevent adoption; storage failure prevents POST',async()=>{
  const f=fixture(),model=await reviewed(f);await model.test(true);
  const other=f.model('human-2');await other.initialize();assert.equal(other.getSnapshot().phase,'choose');
  assert.notEqual(connectCheckpointKey('human-1','server-1',workspace.workspace_id),connectCheckpointKey('human-2','server-1',workspace.workspace_id));
  const broken=fixture(),blocked=await reviewed(broken);broken.storage.setItem=()=>{throw new Error('Storage unavailable');};
  await blocked.test(true);assert.equal(broken.calls.filter(c=>c.name==='testSetup').length,0);
  assert.equal(blocked.getSnapshot().phase,'uncertain');model.dispose();other.dispose();blocked.dispose();
});

test('version check uses the existing operator, retains before POST and recovery only reobserves evidence',async()=>{
  const f=fixture();let ready=false;
  f.api.options=async()=>({...clone(options),options:options.options.map(row=>({...row,technical_state:ready?'READY_FOR_RUNTIME':'NOT_PROBED'}))});
  f.api.checkLocalInstallation=async(executor,body)=>{assert.equal(body.agent_id,'operator-agent');assert.equal(f.storage.values.size,1);ready=true;throw new Error('Lost version response');};
  const model=f.model();await model.initialize();await model.add();model.selectInstallation('candidate-codex_app_server');
  await model.verifyInstallation();assert.equal(model.getSnapshot().phase,'uncertain');await model.recover();
  assert.equal(model.getSnapshot().phase,'configure');assert.equal(f.storage.values.size,0);assert.equal(f.calls.filter(c=>c.name==='testSetup').length,0);model.dispose();
});

test('Connector bootstrap command is public, host-local and cannot carry URL credentials or pretend localhost is remote',()=>{
  const command=connectorDraftCommand('https://nexus.example.test:8202','powershell');
  assert.equal(command,"okto-nexus-connector connect --server='https://nexus.example.test:8202' --setup-draft 'HOST_DRAFT.json'");
  assert.doesNotMatch(command,/--agent|--credential|--project|--workspace-id/);
  for(const value of ['http://localhost:8202','http://127.0.0.1:8202','https://user:secret@nexus.test','https://nexus.test?token=secret','file:///tmp/file'])assert.throws(()=>connectorDraftCommand(value,'posix'));
});

test('actual short flow renders inline progress and no advanced modal, managed launch or pre-created identity',()=>{
  const html=renderToStaticMarkup(React.createElement(ProjectConnectFlow,{identityKey:'human-1',workspace,serverOrigin:'https://nexus.example.test',onClose(){},onResume(){},onComplete(){},api:fixture().api,storage:store()}));
  assert.match(html,/Connect agent/);assert.match(html,/1\. Connection/);assert.match(html,/2\. Setup/);assert.match(html,/3\. Confirm/);
  assert.doesNotMatch(html,/role="dialog"|agent-connections-|<iframe|Advanced settings/);
});

test('changed bindings and disposed identity never navigate with stale catalog context',async()=>{
  const changed=fixture({async binding(){return {...row(),binding_revision:9};}}),model=changed.model();
  changed.setCatalog([row()]);
  await model.initialize();assert.equal(await model.resume(row()),null);assert.match(model.getSnapshot().error,/changed/);model.dispose();
  let respond;const f=fixture({binding(){return new Promise(resolve=>{respond=resolve;});}}),old=f.model();f.setCatalog([row()]);await old.initialize();
  const pending=old.resume(row());await Promise.resolve();old.dispose();respond(row());assert.equal(await pending,null);
});

test('foreign, repeated, truncated and over-budget directories never expose a partial catalog or permit Add',async()=>{
  for(const patch of [page=>({...page,version:true}),page=>({...page,scope:{workspace_id:'foreign'}}),page=>({...page,total:2}),page=>({...page,items:[row(),row()],total:2}),
    page=>({...page,items:[{...row(),workspace_id:'foreign'}]}),page=>({...page,total_is_exact:false})]) {
    const f=fixture(),original=f.api.connectionCatalog;f.setCatalog([row()]);f.api.connectionCatalog=async(...args)=>patch(await original(...args));
    const model=f.model();await model.initialize();assert.notEqual(model.getSnapshot().catalogStatus,'ready');assert.equal(model.getSnapshot().catalog.length,0);
    await model.add();assert.equal(f.calls.filter(c=>c.name==='setupDraft').length,0);model.dispose();
  }
  let pages=0;const f=fixture({async connectionCatalog(filters){pages++;return {version:1,server_id:'server-1',scope:filters,revision:'c'.repeat(64),items:[row('codex_app_server','binding-'+pages)],total:10000,total_is_exact:true,has_more:true,next_cursor:'page-'+pages,requires_canonical_revalidation:true,cursor_integrity:'unsigned_scope_checked'};}});
  const model=f.model();await model.initialize();assert.equal(pages,32);assert.equal(model.getSnapshot().catalog.length,0);assert.equal(model.getSnapshot().catalogStatus,'unavailable');model.dispose();
});

test('changing project clears old catalog even when the new scoped request fails',async()=>{
  const f=fixture();f.setCatalog([row()]);f.api.connectionWorkspaces=async()=>({items:[workspace,{workspace_id:'other-project',display_name:'Other'}],has_more:false,next_workspace_id:null});
  const model=f.model();await model.initialize();assert.equal(model.getSnapshot().catalog.length,1);
  f.api.connectionCatalog=async()=>{throw new Error('Unavailable');};await model.selectWorkspace({workspace_id:'other-project',display_name:'Other'});
  assert.equal(model.getSnapshot().catalog.length,0);assert.equal(model.getSnapshot().catalogStatus,'unavailable');model.dispose();
});

test('project directory rejects duplicate identities, host fields and incomplete bounded paging',async()=>{
  for(const page of [{items:[workspace,workspace],has_more:false,next_workspace_id:null},
    {items:[{...workspace,root_realpath:'C:/must-not-import'}],has_more:false,next_workspace_id:null},
    {items:[workspace],has_more:true,next_workspace_id:null}]) {
    const f=fixture({async connectionWorkspaces(){return clone(page);}}),model=f.model();await model.initialize();
    assert.notEqual(model.getSnapshot().phase,'choose');assert.equal(f.calls.filter(c=>c.name==='connectionCatalog').length,0);model.dispose();
  }
  let pages=0;const f=fixture({async connectionWorkspaces(){pages++;const id='workspace-'+String(pages).padStart(3,'0');return {items:[{workspace_id:id,display_name:'Project'}],has_more:true,next_workspace_id:id};}}),model=f.model();
  await model.initialize();assert.equal(pages,32);assert.equal(model.getSnapshot().phase,'loading');model.dispose();
});

test('actual review and Finish visibly disclose Server-wide native policy, exact permissions and dynamic limits',async()=>{
  const f=fixture(),model=await reviewed(f),original=React.useSyncExternalStore;
  React.useSyncExternalStore=()=>model.getSnapshot();
  const render=()=>renderToStaticMarkup(React.createElement(ProjectConnectFlow,{identityKey:'human-1',workspace,serverOrigin:'https://nexus.example.test',onClose(){},onResume(){},onComplete(){},api:f.api,storage:f.storage}));
  try {
    const review=render();assert.match(review,/Server-wide change at Finish/);assert.match(review,/global Server policy change/);
    assert.match(review,/Project assistant/);assert.match(review,/messages per minute/);assert.match(review,/>43</);assert.match(review,/>6</);
    assert.match(review,/17 minutes/);assert.match(review,/9 actions/);assert.match(review,/sha256:ffff/);assert.match(review,/I approve this exact identity/);
    await model.test(true);const finish=render();assert.match(finish,/Apply this exact reviewed identity/);assert.match(finish,/Server-wide native decision policy change/);
    assert.match(finish,/<button[^>]*disabled=""[^>]*>Finish<\/button>/);
  } finally {React.useSyncExternalStore=original;model.dispose();}
});

function renderExistingModel(model,f,extra={}) {
  const exported=load(new URL('../src/projectConnectFlowModel.ts',import.meta.url)),original=exported.ProjectConnectModel;
  exported.ProjectConnectModel=function(){return model;};
  try{return renderToStaticMarkup(React.createElement(ProjectConnectFlow,{identityKey:'human-1',workspace,serverOrigin:'https://nexus.example.test',onClose(){},onResume(){},onComplete(){},api:f.api,storage:f.storage,...extra}));}
  finally{exported.ProjectConnectModel=original;}
}

const flowSource=ts.createSourceFile('ProjectConnectFlow.tsx',readFileSync(new URL('../src/components/onboarding/ProjectConnectFlow.tsx',import.meta.url),'utf8'),ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);
function expressionCode(expression) {return ts.transpileModule('const value='+expression.getText(flowSource),{compilerOptions:{target:ts.ScriptTarget.ES2022}}).outputText+';return value;';}
function actualButtonHandler(label,values) {
  let expression;
  const visit=node=>{if(ts.isJsxElement(node)&&node.openingElement.tagName.getText(flowSource)==='button'&&node.children.some(child=>ts.isJsxText(child)&&child.text.trim()===label)){
    expression=node.openingElement.attributes.properties.find(attr=>ts.isJsxAttribute(attr)&&attr.name.getText(flowSource)==='onClick')?.initializer.expression;
  }ts.forEachChild(node,visit);};visit(flowSource);assert.ok(expression,label);
  return new Function(...Object.keys(values),expressionCode(expression))(...Object.values(values));
}

test('canonical Finish remains visibly Connected until an explicit navigation choice; effects never auto-complete',async()=>{
  const f=fixture(),model=await reviewed(f);await model.test(true);await model.finish();
  const state=model.getSnapshot(),calls=[],effects=[],originalEffect=React.useEffect;
  const facade=Object.create(model);facade.initialize=()=>{};facade.dispose=()=>{};
  React.useEffect=effect=>effects.push(effect);
  let html;
  try{html=renderExistingModel(facade,f,{onComplete:(...args)=>calls.push(args)});}finally{React.useEffect=originalEffect;}
  for(const effect of effects)effect();
  await Promise.resolve();assert.deepEqual(calls,[]);
  assert.match(html,/aria-label="Connection confirmed"/);assert.match(html,/>Connected<\/h3>/);
  assert.match(html,/Fixture project/);assert.match(html,/Fixture Server/);assert.match(html,/>Codex<\/dd>/);
  assert.match(html,/Harness default \(model not specified\)/);
  assert.match(html,/>Open connection<\/button>/);assert.match(html,/>Back to project<\/button>/);
  let transitions=0;
  const values={transition:fn=>{transitions++;fn();},onComplete:(...args)=>calls.push(args),state};
  actualButtonHandler('Open connection',values)();actualButtonHandler('Back to project',values)();
  assert.equal(transitions,2);assert.deepEqual(calls,[[state.result,{openContext:true}],[state.result,{openContext:false}]]);
  assert.equal(f.calls.filter(c=>c.name==='testSetup').length,1);assert.equal(f.calls.filter(c=>c.name==='finishSetup').length,1);model.dispose();
});

test('successful Test is not Connected and Finish still requires separate explicit consent; full review stays in closed details',async()=>{
  const f=fixture(),model=await reviewed(f);await model.test(true);
  const html=renderExistingModel(model,f);
  assert.match(html,/Test passed\. Finish to create this connection\./);assert.doesNotMatch(html,/>Connected<\/h3>/);
  assert.match(html,/<button[^>]*disabled=""[^>]*>Finish<\/button>/);
  const details=html.indexOf('<details><summary>Permissions, limits and technical details');
  assert.ok(details>0);assert.match(html.slice(details),/messages per minute/);assert.match(html.slice(details),/sha256:ffff/);
  assert.ok(html.indexOf('Server-wide change at Finish:')<details);
  assert.equal(f.calls.filter(c=>c.name==='finishSetup').length,0);model.dispose();
});

test('pending indicators follow actual Test and Finish responses; success waits for validated Finish',async()=>{
  const f=fixture();
  let releaseTest,releaseFinish;
  const testGate=new Promise(resolve=>releaseTest=resolve),finishGate=new Promise(resolve=>releaseFinish=resolve);
  const originalTest=f.api.testSetup,originalFinish=f.api.finishSetup;
  f.api.testSetup=async body=>{await testGate;return originalTest(body);};
  f.api.finishSetup=async body=>{await finishGate;return originalFinish(body);};
  const model=await reviewed(f);
  const testing=model.test(true);
  let html=renderExistingModel(model,f);
  assert.match(html,/data-connection-outcome="pending"/);assert.match(html,/Testing reviewed connection/);
  assert.match(html,/lucide-loader-circle/);assert.match(html,/animate-spin motion-reduce:animate-none/);
  assert.doesNotMatch(html,/data-connection-outcome="success"|>Connected<\/h3>/);
  releaseTest();await testing;
  html=renderExistingModel(model,f);
  assert.doesNotMatch(html,/data-connection-outcome="pending"|data-connection-outcome="success"/);
  assert.match(html,/<button[^>]*disabled=""[^>]*>Finish<\/button>/);
  const finishing=model.finish();
  html=renderExistingModel(model,f);
  assert.match(html,/data-connection-outcome="pending"/);assert.match(html,/Saving connection/);
  assert.doesNotMatch(html,/data-connection-outcome="success"|>Connected<\/h3>/);
  releaseFinish();await finishing;
  html=renderExistingModel(model,f);
  assert.match(html,/data-connection-outcome="success"/);assert.match(html,/lucide-circle-check/);
  assert.match(html,/>Connected<\/h3>/);assert.doesNotMatch(html,/data-connection-outcome="pending"/);
  assert.equal(f.calls.filter(c=>c.name==='testSetup').length,1);assert.equal(f.calls.filter(c=>c.name==='finishSetup').length,1);
  model.dispose();
});

test('known test failure and unknown outcomes have distinct graphics without invented success or replay',async()=>{
  for(const known of [false,true]){
    const f=fixture({async testSetup(body){if(!known)throw new Error('response lost');return {test_id:body.client_intent_id,status:'failed',stage:'Test failed',details:[],retryable_failure:false};}});
    const model=await reviewed(f);await model.test(true);
    const html=renderExistingModel(model,f);
    assert.match(html,new RegExp('data-connection-outcome="'+(known?'failure':'unknown')+'"'));
    assert.match(html,known?/Connection test failed/:/Connection outcome unknown/);
    assert.match(html,known?/lucide-circle-x/:/lucide-circle-question-mark/);
    assert.doesNotMatch(html,/data-connection-outcome="success"|data-connection-outcome="pending"/);
    assert.match(html,/Recover existing attempt/);
    assert.equal(f.calls.filter(c=>c.name==='finishSetup').length,0);model.dispose();
  }
});

test('catalog and confirmed connection keep IDs in one closed Technical details entry',async()=>{
  const f=fixture();f.setCatalog([row()]);
  const catalog=f.model();await catalog.initialize();let html=renderExistingModel(catalog,f);
  assert.match(html,/<details><summary>Technical details<\/summary>/);
  assert.ok(html.indexOf('binding-1')>html.indexOf('<details><summary>Technical details'));
  assert.doesNotMatch(html,/<details open/);assert.match(html,/does not start a session, renew authorization or change its configuration/);
  catalog.dispose();
  const model=await reviewed(f);await model.test(true);await model.finish();html=renderExistingModel(model,f);
  assert.equal((html.match(/<summary>Technical details<\/summary>/g)||[]).length,1);
  assert.ok(html.indexOf(model.getSnapshot().result.binding.binding_id)>html.indexOf('<details><summary>Technical details'));
  assert.doesNotMatch(html,/<details open/);assert.match(html,/No project task has been started/);model.dispose();
});

test('review displays an explicitly configured canonical model and never invents a default model',async()=>{
  const f=fixture(),model=await reviewed(f);
  model.editReview();model.customize({harness_settings:{model:'fixture-observed-model'}});model.review();
  const html=renderExistingModel(model,f);
  assert.match(html,/<dt>Model<\/dt><dd[^>]*>fixture-observed-model<\/dd>/);assert.doesNotMatch(html,/Harness default \(model not specified\)/);
  assert.equal(f.calls.filter(c=>['testSetup','finishSetup'].includes(c.name)).length,0);model.dispose();
});

test('missing required Server folder gives a visible error and focuses that exact field before any review or effect',async()=>{
  const f=fixture(),model=await reviewed(f);model.editReview();model.customize({workspace_root:''});
  const state=model.getSnapshot(),before=state.agentId;
  const html=renderExistingModel(model,f);assert.match(html,/Project folder required on the Server/);assert.match(html,/<input[^>]*required=""[^>]*aria-label="Project folder on the Nexus Server"/);
  let reviewExpression,focusExpression;
  const visit=node=>{if(ts.isVariableDeclaration(node)&&node.name.getText(flowSource)==='review')reviewExpression=node.initializer;
    if(ts.isCallExpression(node)&&node.expression.getText(flowSource)==='useEffect'&&node.arguments[0]?.getText(flowSource).includes('field?.closest'))focusExpression=node.arguments[0];
    ts.forEachChild(node,visit);};visit(flowSource);assert.ok(reviewExpression);assert.ok(focusExpression);
  let invalid=null,error='',expanded=false,focused=0;
  new Function('state','setInvalid','setError','setFolderOpen','setCustomize','act','model',expressionCode(reviewExpression))(
    state,value=>invalid=value,value=>error=value,value=>expanded=value,()=>{},()=>assert.fail('must not review'),model)();
  assert.equal(invalid,'folder');assert.match(error,/project folder on the Nexus Server/);assert.equal(expanded,true);
  const details={open:false},field={closest:()=>details,focus:()=>focused++};
  new Function('error','state','invalid','nameField','projectField','folderField','providerField','alert',expressionCode(focusExpression))(
    error,state,invalid,{current:null},{current:null},{current:field},{current:null},{current:null})();
  assert.equal(focused,1);assert.equal(details.open,true);assert.equal(model.getSnapshot().agentId,before);
  assert.equal(f.calls.filter(c=>['testSetup','finishSetup'].includes(c.name)).length,0);model.dispose();
});

test('unconfirmed or foreign complete snapshot cannot display Connected or offer navigation',async()=>{
  const f=fixture(),model=await reviewed(f);await model.test(true);await model.finish();
  const original=model.getSnapshot,result=clone(original().result);result.binding.workspace_id='foreign';
  const facade=Object.create(model);facade.getSnapshot=()=>({...original(),result});
  const html=renderExistingModel(facade,f);assert.doesNotMatch(html,/>Connected<\/h3>|>Back to project<\/button>/);assert.match(html,/saved connection has not been confirmed/);model.dispose();
});

test('UI review preserves canonical Claude provider-home null without imposing a new required field',async()=>{
  const f=fixture(),model=await reviewed(f,'claude_stream');model.editReview();model.customize({provider_home:null});
  const state=model.getSnapshot();let expression;
  const visit=node=>{if(ts.isVariableDeclaration(node)&&node.name.getText(flowSource)==='review')expression=node.initializer;ts.forEachChild(node,visit);};visit(flowSource);
  new Function('state','setInvalid','setError','setFolderOpen','setCustomize','act','model',expressionCode(expression))(
    state,()=>assert.fail('canonical default must remain valid'),()=>assert.fail('must not add provider-home error'),()=>{},()=>{},fn=>fn(),model)();
  assert.equal(model.getSnapshot().phase,'review');assert.equal(model.getSnapshot().request.configuration.provider_home,null);
  assert.match(renderExistingModel(model,f),/Harness default on the Server/);
  assert.equal(f.calls.filter(c=>['testSetup','finishSetup'].includes(c.name)).length,0);model.dispose();
});

test('catalog and summary use public harness names while technical IDs remain in references',async()=>{
  const f=fixture();f.setCatalog([row('codex_app_server','codex-binding'),row('claude_stream','claude-binding'),row('pi_rpc','pi-binding'),row('custom_adapter','custom-binding')]);
  const catalog=f.model();await catalog.initialize();const html=renderExistingModel(catalog,f);
  for(const label of ['Codex','Claude','Pi','custom_adapter'])assert.match(html,new RegExp(' · '+label+'<\\/p>'));
  for(const id of ['codex_app_server','claude_stream','pi_rpc'])assert.match(html,new RegExp('Harness reference: '+id));
  assert.doesNotMatch(html,/ · (codex_app_server|claude_stream|pi_rpc)<\/p>/);catalog.dispose();
  const reviewedModel=await reviewed(f),state=reviewedModel.getSnapshot(),facade=Object.create(reviewedModel);
  facade.getSnapshot=()=>({...state,options:{...state.options,catalog:{...state.options.catalog,runtimes:[]}}});
  assert.match(renderExistingModel(facade,f),/<dd>Codex · Fixture Server<\/dd>/);reviewedModel.dispose();
});

test('foreign test/Finish/recovery results preserve intent and cannot complete another selection',async()=>{
  const testForeign=fixture({async testSetup(){return {test_id:'foreign-intent',status:'succeeded',stage:'Foreign',details:[]};}}),badTest=await reviewed(testForeign);
  await badTest.test(true);assert.equal(badTest.getSnapshot().phase,'uncertain');assert.equal(testForeign.storage.values.size,1);badTest.dispose();
  const finishForeign=fixture(),original=finishForeign.api.finishSetup;finishForeign.api.finishSetup=async body=>({...await original(body),agent_id:'foreign-agent'});
  const badFinish=await reviewed(finishForeign);await badFinish.test(true);await badFinish.finish();assert.equal(badFinish.getSnapshot().phase,'uncertain');assert.equal(finishForeign.storage.values.size,1);
  finishForeign.api.recoverSetup=async()=>({setup_run_id:'foreign-intent',request_hash:'sha256:'+'d'.repeat(64),state:'committed',result:{saved:true}});
  await badFinish.recover();assert.equal(badFinish.getSnapshot().phase,'uncertain');assert.equal(finishForeign.storage.values.size,1);badFinish.dispose();
});

test('checkpoint content excludes inline credentials, environment secrets and MCP material',async()=>{
  const f=fixture(),model=f.model();await model.initialize();await model.add();model.selectInstallation('candidate-codex_app_server');
  assert.throws(()=>model.customize({secret_bindings:{provider:'plain-secret'}}),/protected secret references/);
  assert.throws(()=>model.customize({harness_settings:{api_key:'plain-secret'}}),/Credentials/);
  model.review();await model.test(true);
  const saved=[...f.storage.values.values()][0];assert.doesNotMatch(saved,/plain-secret|mcp_preset|credential|environment/);
  assert.equal(JSON.parse(saved).request.client_intent_id,model.getSnapshot().request.client_intent_id);model.dispose();
});

test('additive RuntimeApi wrappers use canonical dashboard routes and direct JSON without launching tests',async()=>{
  const {runtimeApi}=load(new URL('../src/runtimeApi.ts',import.meta.url));
  const previous=globalThis.fetch,calls=[];
  globalThis.fetch=async(url,init)=>{calls.push({url,init});return new Response(JSON.stringify({items:[],has_more:false,next_workspace_id:null}),{status:200});};
  try {
    await runtimeApi.setupDraft('new agent');await runtimeApi.connectionWorkspaces('workspace-previous');
    await runtimeApi.connectionCatalog({workspace_id:workspace.workspace_id},'cursor-value');
    assert.match(calls[0].url,/\/api\/v1\/runtime-management\/connections\/setup\/new%20agent\?new_agent_draft=true$/);
    assert.match(calls[1].url,/connections\/workspaces\?limit=100&after_workspace_id=workspace-previous$/);
    assert.match(calls[2].url,/connections\/catalog\?workspace_id=logical-project&limit=100&cursor=cursor-value$/);
    assert.ok(calls.every(call=>call.init.method==='GET'&&call.init.cache==='no-store'));
  } finally {globalThis.fetch=previous;}
});
