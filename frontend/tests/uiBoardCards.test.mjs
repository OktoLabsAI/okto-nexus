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
  const code=ts.transpileModule(readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText;
  const localRequire=name=>{if(name.endsWith('.css'))return {};if(!name.startsWith('.'))return require(name);const path=['.ts','.tsx'].map(ext=>new URL(name+ext,url)).find(p=>existsSync(p));assert.ok(path,name);return load(path);};
  new Function('require','module','exports',code)(localRequire,module,module.exports);return module.exports;
}
const {HomeBoardCards}=load(new URL('../src/components/home/HomeBoardCards.tsx',import.meta.url));
const {HomeEntryRow}=load(new URL('../src/components/home/HomeCards.tsx',import.meta.url));
const item=(id,patch={})=>({id,group_id:'group',entry_revision:'entry-rev',kind:'work',workspace_id:'ws',agent_id:'agent',title:'Work '+id,display_state:'running',evidence:'confirmed',agent_label:'Collaborator',harness_label:'codex_app_server',host_label:'Host',state_since:null,
  sessions:[],sessions_total:0,has_more_sessions:false,sessions_cursor:null,attention_preview:[],attention_total:0,has_more_attention:false,attention_refs:[],attention_cursor:null,
  results_preview:[],results_total:0,has_more_results:false,result_refs:[],results_cursor:null,result_tracking:'not_applicable',external:[],
  target:{kind:'handoff',server_id:'server',workspace_id:'ws',handoff_id:id},...patch});
const page=items=>({items,total:items.length,total_is_exact:true,has_more:false,next_cursor:null});
const noop=()=>{};
function render(board,initialLoading=false){return renderToStaticMarkup(React.createElement(HomeBoardCards,{board,initialLoading,blocked:false,loading:null,onMore:noop,onFocus:noop,onBlur:noop,
  renderEntry:entry=>React.createElement(HomeEntryRow,{key:entry.id,entry,serverId:'server',presentation:'card',allowContinue:false,stale:false,pendingIds:[],loading:null,
    onMore:noop,onOpen:noop,onContinue:noop,onAttentionOpen:noop,onSeen:noop,onSnooze:noop})}));}

test('one Follow-up always renders three non-tab columns and each work card appears once with related content',()=>{
  const result={id:'delivery',title:'Delivered report',outcome:'SUCCEEDED',verification_state:null,cleanup_state:null,view_state:'not_tracked',workspace_id:'ws',agent_id:'agent',preview:'One delivered report',artifacts:[],attention:null,detail_target:{kind:'result',server_id:'server',workspace_id:'ws',executor_id:'executor',session_id:'session',operation_id:'operation'}};
  const shared=item('work',{sessions:[{server_id:'server',workspace_id:'ws',executor_id:'executor',session_id:'session'}],sessions_total:1,results_preview:[result],results_total:1});
  const markup=render({status:'ready',columns:{active:page([shared]),needs_you:page([]),results:page([item('finished')])}});
  assert.equal((markup.match(/data-testid="home-follow-up"/g)||[]).length,1);
  assert.equal((markup.match(/data-home-column=/g)||[]).length,3);
  assert.equal((markup.match(/data-home-entry="work"/g)||[]).length,1);
  assert.match(markup,/View work/);assert.match(markup,/View session/);assert.match(markup,/View delivery/);assert.match(markup,/One delivered report/);
  assert.doesNotMatch(markup,/role="tab|Open context|Continue this session| hidden=/);
});

test('unknown and forbidden/loading states keep column headers without fabricated empty totals or endless loading',()=>{
  const unknown={items:[],total:null,total_is_exact:false,has_more:false,next_cursor:null};
  const markup=render({status:'partial',columns:{active:unknown,needs_you:unknown,results:unknown}});
  assert.equal((markup.match(/Total unknown/g)||[]).length,3);assert.doesNotMatch(markup,/No active items|0 items/);
  assert.equal((render(null).match(/This column is unavailable/g)||[]).length,3);
  assert.doesNotMatch(render(null),/Loading active/);assert.match(render(null,true),/Loading active/);
});
