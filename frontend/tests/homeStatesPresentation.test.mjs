import assert from 'node:assert/strict';
import test from 'node:test';
import {moduleURL} from './homeR1Support.mjs';
const {deliveryPresentation,harnessBadges,homeCountText}=await import(await moduleURL('homeStatePresentation.ts',{
  './homeStateContracts':await moduleURL('homeStateContracts.ts'),
}));
const count=value=>({value,total_is_exact:value!==null});
const status=patch=>({version:1,connection:'connected',activity:'working',blocking:'none',freshness:'current',as_of:null,state_since:null,reason_code:null,
  pending_actions:count(0),pending_by_kind:Object.fromEntries(['question','approval','decision','verification'].map(k=>[k,count(0)])),
  pending_request_ids:[],has_more_pending_requests:false,pending_requests_cursor:null,running_sessions:count(1),blocked_sessions:count(0),awaiting_native_confirmation:false,...patch});
const semantic=patch=>({version:1,scope:'turn',evidence:'canonical',execution_outcome:'succeeded',task_state:'not_applicable',verification:'not_applicable',verification_evidence_ref:null,
  cleanup:'complete',content_state:'available',historical:false,semantic_revision:'proof-revision',...patch});
const present=patch=>deliveryPresentation(semantic(patch),{outcome:'SUCCEEDED',evidence:'canonical'});
test('Working plus a nonblocking request has two badges with independent meanings',()=>{
  const value=status({pending_actions:count(1),pending_by_kind:{question:count(1),approval:count(0),decision:count(0),verification:count(0)}});
  assert.deepEqual(harnessBadges({operational_status:value,placement_reason:'normal_monitoring'}).map(b=>b.label),['Working','Response pending']);
});
test('Idle and normal one-shot session closure have distinct labels',()=>{
  assert.equal(harnessBadges({operational_status:status({activity:'idle'})})[0].label,'Idle');
  assert.equal(harnessBadges({operational_status:status({activity:'no_active_session',connection:'registered'})})[0].label,'No active session');
});
test('Full blocking shows the dependency type; submitted decision asks for no other response',()=>{
  const blocked=status({activity:'waiting_user',blocking:'full',pending_actions:count(1),pending_by_kind:{question:count(0),approval:count(1),decision:count(0),verification:count(0)}});
  assert.deepEqual(harnessBadges({operational_status:blocked,placement_reason:'human_block_confirmed'}).map(b=>b.label),['Waiting for your approval']);
  const confirming=status({activity:'awaiting_confirmation',blocking:'unknown',awaiting_native_confirmation:true});
  assert.deepEqual(harnessBadges({operational_status:confirming,placement_reason:'awaiting_native_confirmation'}).map(b=>b.label),['Waiting for resume confirmation']);
  assert.deepEqual(harnessBadges({operational_status:status({activity:'recovering',reason_code:'NATIVE_RESPONSE_NOT_APPLIED'}),placement_reason:'monitoring_unconfirmed'}).map(b=>b.label),['Response not applied']);
});
test('A turn result is not a completed task or an invented verification workflow',()=>{
  assert.deepEqual(present({}),{title:'Response available',badges:[]});
  assert.deepEqual(present({task_state:'claimed'}),{title:'Turn result available',badges:['Task not yet completed']});
});
test('A completed task needs a specific proof before the delivery gets a verified seal',()=>{
  assert.deepEqual(present({scope:'handoff',task_state:'completed',verification:'unknown'}),{title:'Task completed',badges:[]});
  assert.deepEqual(present({scope:'handoff',task_state:'completed',verification:'approved',verification_evidence_ref:'canonical-verdict'}),{title:'Task completed',badges:['Delivery verified']});
  assert.deepEqual(present({scope:'handoff',task_state:'verifying',verification:'pending'}),{title:'Delivery available',badges:['Awaiting verification']});
});
test('Failure, cancellation, rejected verification and cleanup have independent meanings',()=>{
  assert.equal(present({execution_outcome:'failed'}).title,'Execution ended with failure');
  assert.equal(present({execution_outcome:'cancelled'}).title,'Execution cancelled');
  assert.equal(present({verification:'rejected',verification_evidence_ref:'proof'}).title,'Delivery not approved');
  assert.deepEqual(present({cleanup:'pending'}),{title:'Response available',badges:['Cleanup pending']});
});
test('Terminal without published output does not claim an available response',()=>{
  assert.deepEqual(present({content_state:'pending'}),{title:'Execution ended',badges:['Output not available yet']});
});
test('A verified historical attempt never completes or verifies the current task',()=>{
  const value=present({scope:'handoff',historical:true,task_state:'completed',verification:'approved',verification_evidence_ref:'previous-proof'});
  assert.notEqual(value.title,'Task completed');assert.deepEqual(value.badges,['Verified previous delivery','Previous attempt']);
});
test('External and legacy fallbacks cannot invent a native verification seal',()=>{
  assert.deepEqual(deliveryPresentation(undefined,{evidence:'reported'}),{title:'Completion reported',badges:['Not verified by Nexus']});
  assert.deepEqual(deliveryPresentation(undefined,{outcome:'COMPLETED',evidence:'canonical'}),{title:'Task completed',badges:[]});
});
test('Summary numbers distinguish known zero, unknown and lower bounds',()=>{
  assert.equal(homeCountText(count(null),'connected'),'connected: unknown');
  assert.equal(homeCountText(count(0),'actions'),'0 actions');
  assert.equal(homeCountText({value:1,total_is_exact:false},'actions'),'At least 1 action');
});
