import {readFile} from 'node:fs/promises';
import assert from 'node:assert/strict';
import test from 'node:test';
import ts from 'typescript';

const source=await readFile(new URL('../src/modalChanges.ts',import.meta.url),'utf8');
const compiled=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText;
const {CapturedModalChanges,afterConfirmedModalChange}=await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`);

test('confirmed verification or decision consumes captured draft changes',async()=>{
  const changes=new CapturedModalChanges();
  changes.capture();changes.capture();
  assert.equal(changes.dirty,true);
  const receipt={status:'COMPLETED'};
  assert.equal(await afterConfirmedModalChange(changes,async()=>receipt),receipt);
  assert.equal(changes.dirty,false);
  changes.capture();assert.equal(changes.dirty,true,'a later form edit still needs a discard decision');
});

test('network failure and unconfirmed conflict preserve the draft guard without retry',async()=>{
  for(const failure of [new Error('Response lost'),Object.assign(new Error('Revision changed'),{status:409})]){
    const changes=new CapturedModalChanges();changes.capture();let calls=0;
    await assert.rejects(afterConfirmedModalChange(changes,async()=>{calls++;throw failure;}),error=>error===failure);
    assert.equal(changes.dirty,true);assert.equal(calls,1);
    // Re-reading the same revision does not confirm or discard any draft.
    changes.checkpoint();assert.equal(changes.dirty,true);
  }
});

test('a mismatched canonical receipt does not consume captured edits',async()=>{
  const changes=new CapturedModalChanges();changes.capture();
  await assert.rejects(afterConfirmedModalChange(changes,async()=>{
    const receipt={handoff_id:'another'};
    if(receipt.handoff_id!=='reviewed')throw new Error('Wrong canonical record');
  }),/Wrong canonical record/);
  assert.equal(changes.dirty,true);
});

test('success from an older request cannot clear edits made while it was pending',async()=>{
  const changes=new CapturedModalChanges();changes.capture();
  let finish;const response=new Promise(resolve=>{finish=resolve;});
  const pending=afterConfirmedModalChange(changes,()=>response);
  changes.capture();finish({status:'approved'});await pending;
  assert.equal(changes.dirty,true);
  changes.reset();assert.equal(changes.dirty,false,'a confirmed newer revision invalidates the remaining draft');
});

test('confirmed revision reset is idempotent and never revives or consumes later edits',()=>{
  const changes=new CapturedModalChanges();changes.capture();const old=changes.checkpoint();
  changes.capture();changes.reset();changes.reset(old);
  assert.equal(changes.dirty,false);
  changes.capture();changes.reset(old);assert.equal(changes.dirty,true);
});

test('the same canonical controls work outside a guarded modal',async()=>{
  assert.equal(await afterConfirmedModalChange(null,async()=>42),42);
  await assert.rejects(afterConfirmedModalChange(null,async()=>{throw new Error('Denied');}),/Denied/);
});
