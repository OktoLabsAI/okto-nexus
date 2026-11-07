import {readFile} from 'node:fs/promises';
import assert from 'node:assert/strict';
import test from 'node:test';
import ts from 'typescript';

const source = await readFile(new URL('../src/attentionNavigation.ts', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022}}).outputText;
const {attentionTarget, readAttentionReference, decideReviewedApproval, approvalReviewKey} =
  await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`);
const occurrence = (source_type, action, values = {}) => ({source_type, source_id:'original', allowed_actions:[action],
  workspace_id:'workspace',agent_id:'peer',executor_id:'executor',operation_id:'operation',session_id:'session',
  message_id:'message',result_id:'result',...values});
const target = (source, action, values) => attentionTarget(occurrence(source, action, values), action);

const externalItem = () => ({source_type: 'external_observation', source_id: 'instance', agent_id: 'peer', workspace_id: 'workspace',
  kind: 'external_completion_unseen', allowed_actions: ['inspect_external_observation'], external_observation: {
    observed_instance_id: 'instance', source_id: 'source', generation: 7, agent_id: 'peer', workspace_id: 'workspace',
    observational_only: true, last_report: {current_completion_ref: 'original-completion'},
  }});

test('external inspection uses the exact instance and preserves the historical completion separately', async () => {
  const item = externalItem();
  const selection = attentionTarget(item, 'inspect_external_observation');
  assert.deepEqual(selection, {kind: 'external_observation', id: 'instance', source: 'source', generation: 7, agent: 'peer', workspace: 'workspace'});
  const calls = [], controller = new AbortController();
  const response = await readAttentionReference({externalObservation: async (...args) => {
    calls.push(args); return {item: {...item.external_observation, last_report: {current_completion_ref: 'new-completion'}}};
  }}, selection, controller.signal);
  assert.deepEqual(calls, [['instance', controller.signal]]);
  assert.equal(response.record.item.last_report.current_completion_ref, 'new-completion');
  assert.equal(item.external_observation.last_report.current_completion_ref, 'original-completion');
});

test('external reports never resolve canonical approval, execution or task controls', () => {
  const item = externalItem();
  for (const action of ['decide_approval', 'decide_native', 'respond_native', 'verify_handoff', 'inspect_operation', 'inspect_result', 'review_authority']) {
    assert.equal(attentionTarget({...item, allowed_actions: [action]}, action).kind, 'unavailable');
  }
  assert.equal(attentionTarget({...item, external_observation: undefined}, 'inspect_external_observation').kind, 'unavailable');
});

test('external source, identity, generation and context mismatch refuse the selection', async () => {
  const item = externalItem(), selection = attentionTarget(item, 'inspect_external_observation');
  for (const field of ['source_id', 'observed_instance_id', 'agent_id', 'workspace_id', 'generation', 'observational_only']) {
    const changed = {...item.external_observation, [field]: field === 'generation' ? 8 : field === 'observational_only' ? false : 'other'};
    await assert.rejects(readAttentionReference({externalObservation: async () => ({item: changed})}, selection), {code: 'OBSERVATION_SELECTION_CHANGED'});
  }
  for (const generation of [0, -1, 1.2, Number.MAX_SAFE_INTEGER + 1]) {
    assert.equal(attentionTarget({...item, external_observation: {...item.external_observation, generation}}, 'inspect_external_observation').kind, 'unavailable');
    await assert.rejects(readAttentionReference({}, {...selection, generation}), {code: 'OBSERVATION_SELECTION_CHANGED'});
  }
});

test('all thirteen actions resolve exact existing canonical records', () => {
  const cases = [
    ['approval','inspect_approval','approval'], ['approval','decide_approval','approval'],
    ['execution_native_request','respond_native','approval'], ['execution_native_request','decide_native','approval'],
    ['handoff','inspect_handoff','handoff'], ['handoff','verify_handoff','handoff'],
    ['execution_operation','inspect_operation','execution'], ['runtime_pending_delivery','inspect_recovery','message'],
    ['delivery_operation','review_authority','delivery'], ['execution_operation','inspect_executor','execution'],
    ['execution_result','inspect_result','execution'], ['runtime_result_maintenance','inspect_cleanup','maintenance'],
    ['message_delivery','inspect_delivery','message'],
  ];
  for (const [source, action, expected] of cases) assert.equal(target(source, action).kind, expected, action);
  assert.equal(target('execution_native_request','review_authority').id,'original');
  assert.equal(target('execution_operation','inspect_recovery').operation,'operation');
});

test('manual and mirrored handoff results keep handoff and execution references distinct', () => {
  assert.equal(target('handoff_result','inspect_handoff').id,'original');
  assert.equal(target('handoff_result','inspect_result').operation,'operation');
  assert.equal(target('handoff_result','inspect_result',{executor_id:null}).kind,'unavailable');
  assert.equal(target('handoff_result','inspect_handoff',{executor_id:null,operation_id:null}).kind,'handoff');
});

test('disconnected work uses its emitted execution_operation, not its internal executor episode anchor', async () => {
  // sqlite/attention_operations.py emits one occurrence per pending operation;
  // execution_executor is only the durable episode anchor joined by that SELECT.
  const item={kind:'executor_disconnected_with_work',source_type:'execution_operation',source_id:'operation',
    allowed_actions:['inspect_executor','inspect_recovery'],agent_id:'peer',executor_id:'executor',
    operation_id:'operation',session_id:'session',workspace_id:'workspace',message_id:null,result_id:null};
  const {api,calls}=readers();
  for (const action of item.allowed_actions) {
    const resolved=attentionTarget(item,action);
    assert.deepEqual(resolved,{kind:'execution',agent:'peer',executor:'executor',operation:'operation',
      session:'session',workspace:'workspace'});
    await readAttentionReference(api,resolved);
  }
  assert.deepEqual(calls.map(call=>call.slice(0,4)),[
    ['agentRuntimeExecution','peer','operation','executor'],['agentRuntimeExecution','peer','operation','executor']]);
  assert.equal(attentionTarget({...item,source_type:'execution_executor',source_id:'["server","executor"]',operation_id:null},
    'inspect_executor').kind,'unavailable');
});

test('runtime recovery opens its original message without requiring an execution or session', async () => {
  // The real pending-delivery source has no admitted operation or executor yet.
  const item={kind:'runtime_recovery_attention',source_type:'runtime_pending_delivery',source_id:'delivery',
    allowed_actions:['inspect_recovery'],agent_id:'peer',workspace_id:'workspace',message_id:'message',
    executor_id:null,operation_id:null,session_id:null,result_id:null};
  const resolved=attentionTarget(item,'inspect_recovery');
  assert.deepEqual(resolved,{kind:'message',id:'message',workspace:'workspace'});
  const {api,calls}=readers();await readAttentionReference(api,resolved);
  assert.deepEqual(calls,[['message','message',undefined]]);
  assert.equal(attentionTarget({...item,message_id:null},'inspect_recovery').kind,'unavailable');
});

test('minimal references emitted by every other collector retain their canonical navigation', () => {
  const minimal={agent_id:null,workspace_id:null,executor_id:null,operation_id:null,session_id:null,message_id:null,result_id:null};
  const cases=[
    {source_type:'approval',actions:['inspect_approval','decide_approval'],kind:'approval'},
    {source_type:'execution_native_request',actions:['inspect_approval','respond_native','decide_native','review_authority'],kind:'approval'},
    {source_type:'handoff',actions:['inspect_handoff','verify_handoff'],kind:'handoff',workspace_id:'workspace'},
    {source_type:'handoff_result',actions:['inspect_handoff'],kind:'handoff',workspace_id:'workspace'},
    {source_type:'message_delivery',actions:['inspect_delivery'],kind:'message',message_id:'message',workspace_id:'workspace'},
    {source_type:'delivery_operation',actions:['inspect_operation','review_authority'],kind:'delivery',operation_id:'operation',workspace_id:'workspace'},
    {source_type:'runtime_result_maintenance',actions:['inspect_cleanup'],kind:'maintenance'},
    {source_type:'execution_operation',actions:['inspect_operation','inspect_recovery','review_authority'],kind:'execution',
      agent_id:'peer',executor_id:'executor',operation_id:'operation'},
    {source_type:'execution_result',actions:['inspect_result'],kind:'execution',agent_id:'peer',executor_id:'executor',operation_id:'operation'},
  ];
  for (const {actions,kind,...metadata} of cases) {
    const item={...minimal,...metadata,source_id:'original',allowed_actions:actions};
    for (const action of actions) assert.equal(attentionTarget(item,action).kind,kind,`${metadata.source_type}/${action}`);
  }
});

test('missing scope and unavailable actions never select a first session or another record', () => {
  for (const missing of ['agent_id','executor_id','operation_id'])
    assert.equal(target('execution_operation','inspect_operation',{[missing]:null}).kind,'unavailable');
  assert.equal(target('handoff','inspect_handoff',{workspace_id:null}).kind,'unavailable');
  assert.equal(target('message_delivery','inspect_delivery',{message_id:null}).kind,'unavailable');
  assert.equal(target('delivery_operation','review_authority',{operation_id:null}).kind,'unavailable');
  assert.equal(target('approval','inspect_approval',{source_id:''}).kind,'unavailable');
  assert.equal(attentionTarget(occurrence('approval','inspect_approval'),'decide_approval').kind,'unavailable');
});

function readers() {
  const calls=[];
  const response = {
    approvalDetail:{approval_id:'original',workspace_id:'workspace'},
    handoffs:{items:[{handoff_id:'original',workspace_id:'workspace'}]},
    message:{message_id:'message',workspace_id:'workspace'},
    agentRuntimeExecution:{operation_id:'operation',scope:{agent_id:'peer',executor_id:'executor',session_id:'session',workspace_id:'workspace'}},
    runtimeOperationInspection:{items:[{operation_id:'operation',workspace_id:'workspace',agent_id:'peer'}]},
    inspectRuntimeMaintenance:{maintenance:{maintenance_id:'original',result_id:'result',workspace_id:'workspace',agent_id:'peer'}},
  };
  const api = new Proxy({}, {get: (_, name) => {
    if (!(name in response)) throw new Error(`Productive or unexpected API method: ${String(name)}`);
    return async (...args) => {calls.push([name,...args]);return response[name];};
  }});
  return {api,calls,response};
}

test('opening every target only invokes canonical inspection methods, including cleanup inspect', async () => {
  const {api,calls}=readers();
  for (const [source,action] of [['approval','decide_approval'],['handoff','verify_handoff'],['message_delivery','inspect_delivery'],
    ['execution_result','inspect_result'],['delivery_operation','review_authority'],['runtime_result_maintenance','inspect_cleanup']])
    await readAttentionReference(api,target(source,action));
  assert.deepEqual(calls.map(row=>row[0]),['approvalDetail','handoffs','message','agentRuntimeExecution','runtimeOperationInspection','inspectRuntimeMaintenance']);
  assert.deepEqual(calls[1],['handoffs','workspace',{handoff_id:'original'},undefined]);
  assert.deepEqual(calls[3].slice(0,4),['agentRuntimeExecution','peer','operation','executor']);
  assert.equal(calls[5][1],'original');
});

test('empty, duplicate or out-of-scope handoff and delivery responses fail closed', async () => {
  for (const [source,action,method,field] of [['handoff','inspect_handoff','handoffs','handoff_id'],
    ['delivery_operation','inspect_operation','runtimeOperationInspection','operation_id']]) {
    for (const items of [[],[{[field]:'wrong',workspace_id:'workspace'}],
      [{[field]:source==='handoff'?'original':'operation',workspace_id:'another'}],
      [{[field]:'original'},{[field]:'another'}]]) {
      const {api,response}=readers();response[method]={items};
      await assert.rejects(readAttentionReference(api,target(source,action)),/no longer/);
    }
  }
});

test('all execution scope fields and maintenance receipt references are revalidated', async () => {
  for (const field of ['agent_id','executor_id','workspace_id','session_id']) {
    const {api,response}=readers();response.agentRuntimeExecution.scope[field]='other';
    await assert.rejects(readAttentionReference(api,target('execution_result','inspect_result')),/scope/);
  }
  for (const field of ['maintenance_id','result_id','workspace_id','agent_id']) {
    const {api,response}=readers();response.inspectRuntimeMaintenance.maintenance[field]='other';
    await assert.rejects(readAttentionReference(api,target('runtime_result_maintenance','inspect_cleanup')),/receipt/);
  }
});

test('original approval and message scope are checked, and unavailable target performs no API call', async () => {
  for (const [source,action,method] of [['approval','inspect_approval','approvalDetail'],['message_delivery','inspect_delivery','message']]) {
    const {api,response}=readers();response[method].workspace_id='another';
    await assert.rejects(readAttentionReference(api,target(source,action)),/no longer matches/);
  }
  const {api,calls}=readers();
  await assert.rejects(readAttentionReference(api,{kind:'unavailable',reason:'Missing original reference'}),/Missing/);
  assert.deepEqual(calls,[]);
});

test('historical execution is read by exact operation without enumerating current sessions', async () => {
  const {api,calls}=readers();
  const value=await readAttentionReference(api,target('execution_result','inspect_result',{session_id:null}));
  assert.equal(value.record.operation_id,'operation');assert.equal(calls.length,1);
  assert.equal(calls[0][0],'agentRuntimeExecution');
});

test('authorization failures propagate without fallback, retry or retaining another record', async () => {
  const failure=Object.assign(new Error('Revoked'),{status:403});let calls=0;
  await assert.rejects(readAttentionReference({message:async()=>{calls++;throw failure;}},target('message_delivery','inspect_delivery')),error=>error===failure);
  assert.equal(calls,1);
});

test('each canonical inspection forwards its cancellation signal', async () => {
  const {api,calls}=readers();const controller=new AbortController();
  for (const [source,action] of [['approval','inspect_approval'],['handoff','inspect_handoff'],['message_delivery','inspect_delivery'],
    ['execution_result','inspect_result'],['delivery_operation','review_authority'],['runtime_result_maintenance','inspect_cleanup']])
    await readAttentionReference(api,target(source,action),controller.signal);
  for (const call of calls) assert.equal(call.at(-1),controller.signal);
});

test('generic decisions send the reviewed revision and never retry a conflict', async () => {
  const calls=[];const conflict=Object.assign(new Error('Changed'),{status:409});
  const api={decideApproval:async(...args)=>{calls.push(args);throw conflict;}};
  await assert.rejects(decideReviewedApproval(api,{approval_id:'approval',decision_revision:7},'reject','reviewed reason'),error=>error===conflict);
  assert.deepEqual(calls,[['approval','reject','reviewed reason',undefined,7]]);
});

test('missing or invalid approval revision cannot submit a decision', async () => {
  let calls=0;const api={decideApproval:async()=>{calls++;}};
  for (const revision of [undefined,null,-1,0.1,'1'])
    await assert.rejects(decideReviewedApproval(api,{approval_id:'approval',decision_revision:revision},'approve'),/revision/);
  assert.equal(calls,0);
});

test('same revision preserves native draft identity; native revision, digest and CAS changes reset it', () => {
  const detail={approval_id:'approval',decision_revision:2,action:'execution.native.respond',request_payload:{kwargs:{
    expected_revision:4,request_hash:'hash',cas_token:'token',approval_key:{session_id:'session',agent_id:'peer'}}}};
  const key=approvalReviewKey(detail);
  assert.equal(approvalReviewKey({...detail,updated_at:'later'}),key);
  assert.equal(approvalReviewKey({...detail,request_payload:{kwargs:{...detail.request_payload.kwargs,
    approval_key:{agent_id:'peer',session_id:'session'}}}}),key);
  assert.notEqual(approvalReviewKey({...detail,decision_revision:3}),key);
  for (const [field,value] of [['expected_revision',5],['request_hash','new-hash'],['cas_token','new-token']])
    assert.notEqual(approvalReviewKey({...detail,request_payload:{kwargs:{...detail.request_payload.kwargs,[field]:value}}}),key);
});
