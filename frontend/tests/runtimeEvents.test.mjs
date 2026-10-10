import {readFile} from 'node:fs/promises';
import assert from 'node:assert/strict';
import test from 'node:test';
import ts from 'typescript';
const source = await readFile(new URL('../src/runtimeEvents.ts',import.meta.url),'utf8');
const compiled = ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText;
const {appendTail,validateEventPage} = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`);
const scope = {server_id:'s',executor_id:'host',session_id:'session',agent_id:'a',binding_id:'b',workspace_id:'w',workspace_binding_id:'wb'};
const event = sequence => ({server_id:'s',executor_id:'host',session_id:'session',stream_epoch:'epoch',sequence});
const page = {scope,stream_epoch:'epoch',events:[event(51),event(52)],count:2,next_after_sequence:52,committed_contiguous:52,has_more:false};
test('tail validates exact cursor, session, executor and epoch before displaying events',()=>{
  validateEventPage(page,scope,50,'epoch');
  assert.throws(()=>validateEventPage(page,{...scope,executor_id:'remote'},50,'epoch'));
  assert.throws(()=>validateEventPage(page,scope,51,'epoch'));
  assert.throws(()=>validateEventPage(page,scope,50,'other-epoch'));
  assert.throws(()=>validateEventPage({...page,events:[event(51),event(53)]},scope,50,'epoch'));
});
test('tail is bounded and does not duplicate events on refresh',()=>{
  const old=Array.from({length:200},(_,i)=>event(i+1));
  const next=appendTail(old,[event(200),event(201),event(202)]);
  assert.equal(next.length,200);assert.equal(next[0].sequence,3);assert.equal(next.at(-1).sequence,202);
  assert.equal(new Set(next.map(e=>e.sequence)).size,200);
});
