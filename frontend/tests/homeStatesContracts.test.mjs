import assert from 'node:assert/strict';
import test from 'node:test';
import {moduleURL} from './homeR1Support.mjs';
const {validHomeStateCount,validHomeOperationalStatus,validHomeDeliverySemantics,validHomePlacement}=await import(await moduleURL('homeStateContracts.ts'));
const count=value=>({value,total_is_exact:value!==null});
const status=()=>({version:1,connection:'connected',activity:'working',blocking:'none',freshness:'current',
  as_of:'2026-11-17T00:00:00Z',state_since:null,reason_code:null,pending_actions:count(0),
  pending_by_kind:Object.fromEntries(['question','approval','decision','verification'].map(k=>[k,count(0)])),
  pending_request_ids:[],has_more_pending_requests:false,pending_requests_cursor:null,
  running_sessions:count(1),blocked_sessions:count(0),awaiting_native_confirmation:false});
const delivery=()=>({version:1,scope:'turn',evidence:'canonical',execution_outcome:'succeeded',task_state:'not_applicable',
  verification:'not_applicable',verification_evidence_ref:null,cleanup:'complete',content_state:'available',historical:false,semantic_revision:'r1'});

test('Count distinguishes unknown from a proven zero and rejects invalid exactness',()=>{
  assert.ok(validHomeStateCount(count(null)));assert.ok(validHomeStateCount(count(0)));
  for(const value of [{value:null,total_is_exact:true},count(-1),count(1.5),count(Infinity),count(true)])assert.equal(validHomeStateCount(value),false);
});
test('Working can be positively known while another count remains partial',()=>{
  const value=status();value.blocked_sessions=count(null);value.pending_actions=count(null);
  assert.ok(validHomeOperationalStatus(value));
});
test('Idle cannot be synthesized from registration, stale coverage or pending confirmation',()=>{
  const value={...status(),activity:'idle',running_sessions:count(0)};
  assert.ok(validHomeOperationalStatus(value));
  for(const patch of [{connection:'registered'},{freshness:'stale'},{blocking:'unknown'},{awaiting_native_confirmation:true}])
    assert.equal(validHomeOperationalStatus({...value,...patch}),false);
});
test('Pending preview is unique and must expose its continuation',()=>{
  const value={...status(),pending_actions:count(7),pending_request_ids:['request1'],has_more_pending_requests:true,pending_requests_cursor:'scoped-cursor'};
  assert.ok(validHomeOperationalStatus(value));
  assert.equal(validHomeOperationalStatus({...value,pending_requests_cursor:null}),false);
  assert.equal(validHomeOperationalStatus({...value,pending_request_ids:['request1','request1']}),false);
  assert.equal(validHomeOperationalStatus({...value,pending_by_kind:{}}),false);
});
test('Confirmation is a separate placement and not another human block boolean',()=>{
  assert.ok(validHomePlacement('awaiting_native_confirmation'));
  const value={...status(),activity:'awaiting_confirmation',blocking:'unknown',awaiting_native_confirmation:true};
  assert.ok(validHomeOperationalStatus(value));assert.equal(value.pending_actions.value,0);
});
test('Version and enum drift fail closed rather than introducing Idle or permission',()=>{
  for(const patch of [{version:2},{activity:'registered'},{connection:'running'},{awaiting_native_confirmation:1}])
    assert.equal(validHomeOperationalStatus({...status(),...patch}),false);
  assert.equal(validHomePlacement('approved'),false);
});
test('Turn success does not need a task or verification workflow',()=>{
  const value=delivery();assert.ok(validHomeDeliverySemantics(value));assert.equal(value.task_state,'not_applicable');
});
test('Completed handoff without positive verification evidence has no verified proof',()=>{
  const value={...delivery(),scope:'handoff',task_state:'completed',verification:'unknown'};
  assert.ok(validHomeDeliverySemantics(value));
  assert.equal(validHomeDeliverySemantics({...value,verification:'approved'}),false);
  assert.ok(validHomeDeliverySemantics({...value,verification:'approved',verification_evidence_ref:'verification:opaque'}));
});
test('External report cannot carry a native approved seal',()=>{
  const value={...delivery(),scope:'external_report',evidence:'reported',verification:'unknown'};
  assert.ok(validHomeDeliverySemantics(value));
  assert.equal(validHomeDeliverySemantics({...value,verification:'approved',verification_evidence_ref:'forged'}),false);
});
test('Delivery unknown schema is not mistaken for success',()=>{
  for(const patch of [{version:2},{verification:'COMPLETED'},{cleanup:'SUCCEEDED'},{historical:'false'},{semantic_revision:''}])
    assert.equal(validHomeDeliverySemantics({...delivery(),...patch}),false);
});
