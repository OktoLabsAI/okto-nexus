import assert from 'node:assert/strict';
import {existsSync,readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import test from 'node:test';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import ts from 'typescript';
const require=createRequire(import.meta.url),modules=new Map();
function load(url){
  const filename=fileURLToPath(url);if(modules.has(filename))return modules.get(filename).exports;
  const module={exports:{}};modules.set(filename,module);
  const code=ts.transpileModule(readFileSync(filename,'utf8'),{fileName:filename,compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText;
  const localRequire=name=>{if(name.endsWith('.css'))return {};if(!name.startsWith('.'))return require(name);
    const path=['.ts','.tsx','/index.ts'].map(ext=>new URL(name+ext,url)).find(p=>existsSync(p));assert.ok(path,name);return load(path);};
  new Function('require','module','exports',code)(localRequire,module,module.exports);return module.exports;
}
const {initialEntrySession,assertEntryInspectionPage,occurrenceSession}=load(new URL('../src/homeEntryInspection.ts',import.meta.url));
const {HomeEntryInspection}=load(new URL('../src/components/home/HomeEntryInspection.tsx',import.meta.url));
const target={kind:'handoff',server_id:'server',workspace_id:'ws',handoff_id:'handoff'};
const session=id=>({server_id:'server',executor_id:'executor',workspace_id:'ws',session_id:id});
const entry={id:'entry',title:'Work from another agent',agent_id:'implementer',agent_label:'Implementer',host_label:'Host',harness_label:'Codex',
  sessions:[session('one'),session('two')],sessions_total:2,sessions_cursor:null,has_more_sessions:false,
  attention_preview:[],attention_cursor:null,results_preview:[],results_cursor:null,external:[],as_of:'2026-11-16T12:00:00Z'};
const selection={groupId:'group',entry,revision:'rev',filters:{workspace_id:'ws'}};
const page={version:1,server_id:'server',partition:'sessions',group_id:'group',entry_id:'entry',revision:'rev',status:'ready',
  scope:{workspace_id:'ws',quick:'active',include_recent_results:true},items:[]};

test('multiple or incomplete session relations require explicit choice; a proven unique relation can open',()=>{
  assert.equal(initialEntrySession(entry,target),null);
  assert.equal(initialEntrySession({...entry,sessions:[session('one')],sessions_total:null},target),null);
  assert.deepEqual(initialEntrySession({...entry,sessions:[session('one')],sessions_total:1},target),session('one'));
  assert.deepEqual(initialEntrySession(entry,{kind:'session',...session('two')}),session('two'));
  assert.deepEqual(initialEntrySession(entry,{kind:'execution',...session('two'),operation_id:'exact-op'}),session('two'));
});

test('panel pagination rejects foreign parent, scope, revision and hidden default changes',()=>{
  assert.doesNotThrow(()=>assertEntryInspectionPage(page,selection,'server','sessions','rev'));
  for(const delta of [{server_id:'foreign'},{group_id:'other'},{entry_id:'other'},{partition:'results'},{revision:'changed'},
    {scope:{...page.scope,workspace_id:'other'}},{scope:{...page.scope,include_recent_results:false}},
    {scope:{...page.scope,agent_id:'other'}},{status:'unavailable'}])
    assert.throws(()=>assertEntryInspectionPage({...page,...delta},selection,'server','sessions','rev'));
});

test('one contextual panel composes work and exact session choice without a runtime directory or nested dialog',()=>{
  const html=renderToStaticMarkup(React.createElement(HomeEntryInspection,{selection,target,serverId:'server',workspace:'ws',onClose(){},onChanged(){},
    renderRecord:()=>React.createElement('p',null,'Original work from the canonical record')}));
  assert.match(html,/Work from another agent/);assert.match(html,/Choose the exact session/);
  assert.match(html,/Original work from the canonical record/);assert.match(html,/value=""/);
  assert.doesNotMatch(html,/<dialog|Running instances|Last 10 completed|latest session|Session execution output/);
});

test('a question uses its own explicit session and external or missing context never adopts a sibling',()=>{
  const item={source_type:'execution_native_request',session_id:'question-session',executor_id:'question-host',workspace_id:'ws'};
  assert.deepEqual(occurrenceSession(item,'server'),{server_id:'server',session_id:'question-session',executor_id:'question-host',workspace_id:'ws'});
  assert.equal(occurrenceSession({...item,source_type:'external_observation'},'server'),null);
  assert.equal(occurrenceSession({...item,session_id:null},'server'),null);
});
