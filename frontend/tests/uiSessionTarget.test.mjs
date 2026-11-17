import assert from 'node:assert/strict';
import test from 'node:test';
import {moduleURL} from './homeR1Support.mjs';
const {encodeHomeTarget, decodeHomeTarget, homeTargetSearch, resolveHomeTarget, homeInspectionTarget} = await import(await moduleURL('homeNavigation.ts'));
const target={kind:'session',server_id:'server:/one',executor_id:'host:/one',workspace_id:'project & one',session_id:'idle:/one'};
const context={...target,binding_id:'binding',workspace_binding_id:'workspace-binding',agent_id:'A',lifecycle_state:'CLOSED'};
delete context.kind;
const resolved=(patch={})=>({version:1,target,available:true,source_revision:'r1',agent_id:'A',session_context:context,...patch});

test('session without operation roundtrips old URL mechanism with exact opaque identifiers',()=>{
  assert.deepEqual(decodeHomeTarget(encodeHomeTarget(target)),target);
  assert.deepEqual(decodeHomeTarget(new URLSearchParams(homeTargetSearch(target)).get('home_target')),target);
  assert.ok(!Object.hasOwn(decodeHomeTarget(encodeHomeTarget(target)),'operation_id'));
  for(const patch of [{operation_id:'fake'},{workspace_id:null},{executor_id:''},{session_id:null},{session_id:1},{command:'run'},{kind:'session/latest'}])
    assert.equal(decodeHomeTarget(JSON.stringify({...target,...patch})),null);
});

test('two sessions of same identity stay distinct and resolved tuple/binding context is mandatory',async()=>{
  const expected={server_id:target.server_id,workspace_id:target.workspace_id};
  const one=await resolveHomeTarget({target:async()=>resolved()},target,expected);
  const twoTarget={...target,session_id:'idle:/two'};
  const two=await resolveHomeTarget({target:async()=>resolved({target:twoTarget,session_context:{...context,session_id:twoTarget.session_id}})},twoTarget,expected);
  assert.notEqual(one.session_context.session_id,two.session_context.session_id);
  for(const patch of [{session_context:undefined},{session_context:{...context,executor_id:'other'}},
    {session_context:{...context,workspace_id:'other'}},{session_context:{...context,session_id:'latest'}},
    {session_context:{...context,binding_id:''}},{agent_id:'other'}])
    await assert.rejects(resolveHomeTarget({target:async()=>resolved(patch)},target,expected));
});

test('session scope is rejected before HTTP and missing target cannot become execution/latest',async()=>{
  let calls=0;const client={target:async()=>{calls++;return resolved();}};
  await assert.rejects(resolveHomeTarget(client,target,{server_id:'other',workspace_id:null}));
  await assert.rejects(resolveHomeTarget(client,target,{server_id:target.server_id,workspace_id:'other'}));
  assert.equal(calls,0);
  const inspector=homeInspectionTarget(resolved());
  assert.equal(inspector.kind,'session');assert.equal(inspector.context.session_id,target.session_id);
  assert.ok(!Object.hasOwn(inspector,'operation'));
});

test('connection target preserves exact binding identity without requiring a session',async()=>{
  const connection={kind:'connection',server_id:target.server_id,executor_id:target.executor_id,workspace_id:target.workspace_id,binding_id:'binding',agent_id:'A'};
  const c={server_id:target.server_id,executor_id:target.executor_id,workspace_id:target.workspace_id,binding_id:'binding',workspace_binding_id:'wxb',agent_id:'A'};
  assert.deepEqual(decodeHomeTarget(encodeHomeTarget(connection)),connection);
  const api={target:async()=>({version:1,available:true,source_revision:'r',target:connection,agent_id:'A',connection_context:c})};
  await resolveHomeTarget(api,connection,{server_id:target.server_id,workspace_id:null});
  await assert.rejects(resolveHomeTarget({target:async()=>({...await api.target(),connection_context:{...c,binding_id:'foreign'}})},connection,{server_id:target.server_id,workspace_id:null}));
});
