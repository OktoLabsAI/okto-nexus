import {mkdtemp,readFile,writeFile,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {pathToFileURL} from 'node:url';
import assert from 'node:assert/strict';
import test from 'node:test';
import ts from 'typescript';

const temporary=await mkdtemp(join(tmpdir(),'nexus-presentation-'));
let presentEvents;
try {
  await writeFile(join(temporary,'package.json'),' {"type":"module"}');
  for(const name of ['model','codex','claude','pi','index']) {
    const source=await readFile(new URL(`../src/runtimePresentation/${name}.ts`,import.meta.url),'utf8');
    const compiled=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText;
    await writeFile(join(temporary,`${name}.js`),compiled.replace(/from '(\.\/\w+)'/g,"from '$1.js'"));
  }
  ({presentEvents}=await import(pathToFileURL(join(temporary,'index.js')).href));
} finally {await rm(temporary,{recursive:true,force:true});}
const events=rows=>rows.map(([native_type,payload,category='tool_activity'],index)=>({
  native_type,payload,category,sequence:index+1,stream_epoch:'epoch',received_at:'2026-10-13T15:00:00Z',
  server_id:'server',executor_id:'executor',session_id:'session',
}));

test('Codex joins streaming text and snapshots and pairs independent tool calls',()=>{
  const actions=presentEvents(events([
    ['item/started',{item:{id:'m1',type:'agentMessage',text:''}}],
    ['item/agentMessage/delta',{itemId:'m1',delta:'Hello '}],
    ['item/agentMessage/delta',{itemId:'m1',delta:'world'}],
    ['item/completed',{item:{id:'m1',type:'agentMessage',text:'Hello world'}}],
    ['item/started',{item:{id:'t1',type:'commandExecution',command:'npm test',cwd:'D:/work'}}],
    ['item/started',{item:{id:'t2',type:'mcpToolCall',server:'docs',tool:'search',arguments:{query:'pool'}}}],
    ['item/completed',{item:{id:'t2',type:'mcpToolCall',server:'docs',tool:'search',result:{content:[{type:'text',text:'Found'}]}}}],
    ['item/completed',{item:{id:'t1',type:'commandExecution',command:'npm test',aggregatedOutput:'All passed',status:'completed'}}],
  ]),'codex_app_server');
  assert.equal(actions.length,3);assert.equal(actions[0].text,'Hello world');
  assert.equal(actions[1].output,'All passed');assert.equal(actions[2].output,'Found');
  assert.equal(actions[2].fields[0].value,'pool');
});

test('Claude renders tool input fragments only once complete and merges assistant snapshots and results',()=>{
  const actions=presentEvents(events([
    ['stream_event:message_start',{event:{message:{id:'m1'}}}],
    ['stream_event:content_block_delta',{text:'Checking'}],
    ['stream_event:content_block_start',{event:{index:1,content_block:{type:'tool_use',id:'tool1',name:'Read',input:{}}}}],
    ['stream_event:content_block_delta',{event:{index:1,delta:{type:'input_json_delta',partial_json:'{"file_'}}}],
    ['stream_event:content_block_delta',{event:{index:1,delta:{type:'input_json_delta',partial_json:'path":"README.md"}'}}}],
    ['assistant',{text:'Checking',raw:{message:{id:'m1',content:[{type:'text',text:'Checking'},{type:'tool_use',id:'tool1',name:'Read',input:{file_path:'README.md'}}]}}}],
    ['user_echo',{message:{content:[{type:'tool_result',tool_use_id:'tool1',content:'Read complete'}]}}],
    ['result:output',{text:'Checking',final:true}],
  ]),'claude_stream');
  assert.equal(actions.length,2);assert.equal(actions[0].text,'Checking');
  assert.equal(actions[1].title,'Read');assert.equal(actions[1].fields[0].value,'README.md');
  assert.equal(actions[1].output,'Read complete');assert.equal(actions[1].status,'completed');
});

test('Pi normalizes user messages, streams, tools, final message and turn echo',()=>{
  const message={role:'assistant',content:[{type:'text',text:'Done'}]};
  const actions=presentEvents(events([
    ['message_start',{message:{role:'user',content:[{type:'text',text:'Run tests'}]}}],
    ['message_end',{message:{role:'user',content:[{type:'text',text:'Run tests'}]}}],
    ['message_start',{message:{role:'assistant'}}],
    ['tool_execution_start',{toolCallId:'t1',toolName:'bash',args:{command:'npm test'}}],
    ['tool_execution_update',{toolCallId:'t1',partialResult:{content:[{type:'text',text:'Running'}]}}],
    ['tool_execution_end',{toolCallId:'t1',result:{content:[{type:'text',text:'Passed'}]},isError:false}],
    ['message_update',{assistantMessageEvent:{type:'text_delta',delta:'Do'}}],
    ['message_update',{assistantMessageEvent:{type:'text_delta',delta:'ne'}}],
    ['message_end',{message}],['turn_end',{message}],
  ]),'pi_rpc');
  assert.equal(actions.length,3);assert.equal(actions[0].kind,'user');
  assert.equal(actions[1].title,'bash');assert.equal(actions[1].output,'Passed');
  assert.equal(actions[2].text,'Done');
});

test('empty events and protocol frames produce no blank activity or JSON',()=>{
  for(const harness of ['codex_app_server','claude_stream','pi_rpc',undefined]) {
    assert.deepEqual(presentEvents(events([['unknown',{}],['unknown',{type:'unknown',args:{},result:[],text:''}]]),harness),[]);
  }
  const actions=presentEvents(events([['unknown',{result:{matches:[{path:'README.md',line:1}]},args:{}}]]));
  assert.equal(actions.length,1);assert.equal(actions[0].fields[0].value,'README.md');
  assert.ok(!JSON.stringify(actions).includes('"value":"{}"'));
});

test('fallback keeps readable errors, approvals and future harness actions without revealing protected fields',()=>{
  const actions=presentEvents(events([
    ['failure',{error:{message:'Connection lost'}},'error'],
    ['approval',{native_approval:{secret:'MUST_NOT_RENDER'},native_approval_display:{params:{command:'npm test'}}},'approval_request'],
    ['future/action',{args:{env:{API_KEY:'MUST_NOT_RENDER'},query:'hello'},result:'{}'}],
  ]));
  assert.equal(actions[0].text,'Message: Connection lost');assert.equal(actions[1].kind,'approval');
  assert.equal(actions[2].fields.length,2);assert.ok(!JSON.stringify(actions).includes('MUST_NOT_RENDER'));
});

test('identical replies in different turns are retained',()=>{
  const actions=presentEvents(events([
    ['agent_start',{delivery_phase:'started'}],['message_start',{}],
    ['message_end',{message:{role:'assistant',content:[{type:'text',text:'OK'}]}}],
    ['agent_start',{delivery_phase:'started'}],['message_start',{}],
    ['message_end',{message:{role:'assistant',content:[{type:'text',text:'OK'}]}}],
  ]),'pi_rpc');
  assert.equal(actions.filter(a=>a.kind==='assistant').length,2);
});

test('partial history pages and unknown harness payloads are safe and bounded',()=>{
  const actions=presentEvents(events([
    ['item/agentMessage/delta',{itemId:'m1',delta:'Partial history'}],
    ['future/action',{output:'\u001b[31mError\u001b[0m',empty:{},large:'a'.repeat(50000)}],
  ]));
  assert.equal(actions[0].text,'Partial history');assert.equal(actions[1].fields[0].value,'Error');
  assert.equal(actions[1].fields[1].value.length,32000);
});

test('Claude authoritative final replaces streamed text while failed tools retain their inputs',()=>{
  const actions=presentEvents(events([
    ['stream_event:message_start',{event:{message:{id:'m'}}}],
    ['stream_event:content_block_delta',{text:'Partial'}],
    ['assistant',{text:'Partial',raw:{message:{id:'m'}}}],
    ['result:output',{text:'Correct final answer'}],
    ['stream_event:content_block_start',{event:{index:0,content_block:{id:'t',name:'Bash',type:'tool_use',input:{command:'npm test'}}}}],
    ['system:permission_denied',{tool_use_id:'t',tool_name:'Bash',message:'Permission denied'}],
  ]),'claude_stream');
  assert.equal(actions.length,2);assert.equal(actions[0].text,'Correct final answer');
  assert.equal(actions[1].status,'failed');assert.equal(actions[1].fields[0].value,'npm test');
});

test('native input requests, aborted replies and empty status notifications stay distinguishable',()=>{
  const actions=presentEvents(events([
    ['extension_ui_request',{method:'setStatus',statusKey:'busy'}],
    ['message_end',{message:{role:'assistant',stopReason:'aborted'}}],
    ['extension_ui_request',{native_approval_display:{params:{question:'Which workspace?'}}},'input_request'],
    ['core.event_pump_failed',{},'error'],
  ]),'pi_rpc');
  assert.equal(actions.length,3);assert.equal(actions[0].title,'Response interrupted');
  assert.equal(actions[1].kind,'approval');assert.equal(actions[1].fields[0].value,'Which workspace?');
  assert.equal(actions[2].kind,'error');
});

for (const [harness,start,delta,terminal,raw] of [
  ['codex_app_server','turn/started','item/agentMessage/delta','turn/completed',{delta:'[NATIVE_TEXT_REDACTED]',itemId:'[NATIVE_TEXT_REDACTED]'}],
  ['claude_stream','system:init','stream_event:content_block_delta','result:success',{text:'[NATIVE_TEXT_REDACTED]'}],
  ['pi_rpc','agent_start','message_update','agent_settled',{assistantMessageEvent:{type:'[NATIVE_TEXT_REDACTED]',delta:'[NATIVE_TEXT_REDACTED]'}}],
]) test(`${harness}: canonical text and terminal holdback replace masked native fields`,()=>{
  const actions=presentEvents(events([
    [start,{delivery_phase:'started'}],
    [delta,{...raw,output_text:''},'text_delta'],
    [delta,{...raw,output_text:'Visible [REDACTED] '},'text_delta'],
    [terminal,{output_text:'answer.',delivery_phase:'terminal',delivery_outcome:'success'},'turn_state'],
  ]),harness);
  assert.equal(actions.filter(a=>a.kind==='assistant').length,1);
  assert.equal(actions.find(a=>a.kind==='assistant').text,'Visible [REDACTED] answer.');
  assert.ok(!JSON.stringify(actions).includes('[NATIVE_TEXT_REDACTED]'));
});

test('canonical snapshots respect empty holdback and never duplicate native Pi final snapshots',()=>{
  const claude=presentEvents(events([
    ['assistant',{text:'[NATIVE_TEXT_REDACTED]',output_text:'Old answer'},'text_snapshot'],
    ['result:output',{text:'[NATIVE_TEXT_REDACTED]',output_text:''},'text_snapshot'],
    ['result:success',{output_text:'OK',delivery_phase:'terminal'},'turn_state'],
  ]),'claude_stream');
  assert.equal(claude.find(a=>a.kind==='assistant').text,'OK');
  const pi=presentEvents(events([
    ['message_update',{output_text:'The res',assistantMessageEvent:{type:'[NATIVE_TEXT_REDACTED]',delta:'[NATIVE_TEXT_REDACTED]'}},'text_delta'],
    ['message_end',{message:{role:'assistant',content:[{type:'text',text:'The result.'}]}}],
    ['agent_settled',{output_text:'ult.',delivery_phase:'terminal'},'turn_state'],
  ]),'pi_rpc');
  assert.equal(pi.filter(a=>a.kind==='assistant').length,1);
  assert.equal(pi.find(a=>a.kind==='assistant').text,'The result.');
});

test('masked-only native fields do not become blank tools or placeholder text',()=>{
  assert.deepEqual(presentEvents(events([['unknown',{text:'[NATIVE_TEXT_REDACTED]',nested:{value:'[NATIVE_TEXT_REDACTED]'}}]])),[]);
});
