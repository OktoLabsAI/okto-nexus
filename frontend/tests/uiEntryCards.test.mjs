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
const {HomeEntryGroupCard,HomeEntryRow,isQuietEntries,freshHomeEntryOccurrence,homeEntriesAnnouncementIds}=load(new URL('../src/components/home/HomeCards.tsx',import.meta.url));
const target={kind:'handoff',server_id:'server',workspace_id:'ws',handoff_id:'handoff'};
const occurrence=()=>({attention_id:'attention1',kind:'verification_pending',category:'action_required',severity:'info',priority:20,agent_id:'A',workspace_id:'ws',
  source_id:'handoff',source_type:'handoff',source_revision:'source1',first_detected_at:'2026-11-16T12:00:00Z',last_changed_at:'2026-11-16T12:00:00Z',
  freshness:'current',resolution:'open',active:true,allowed_actions:['inspect_handoff'],seen_state:{seen:false,snoozed:false,revision:2}});
const entry=(patch={})=>({id:'entry1',kind:'work',workspace_id:'ws',agent_id:'A',title:'One logical task',display_state:'running',evidence:'confirmed',
  agent_label:'Implementer',harness_label:'codex_app_server',host_label:'Build host',state_since:null,target,
  sessions:[],sessions_total:0,has_more_sessions:false,sessions_cursor:null,attention_preview:[],attention_total:0,has_more_attention:false,
  results_preview:[],results_total:0,has_more_results:false,result_tracking:'not_applicable',attention_refs:[],result_refs:[],external:[],...patch});
const group=(patch={})=>({id:'group1',label:'Implementer · project · Build host',children:[entry()],children_total:1,has_more_children:false,...patch});
const page=(patch={})=>({status:'ready',revision:'rev1',items:[group()],total:1,total_is_exact:true,source_status:{work:'ready',attention:'ready',connections:'ready',sessions:'ready'},server_attention:{items:[]},...patch});
const rowProps=(patch={})=>({entry:entry(),serverId:'server',stale:false,pendingIds:[],loading:null,onMore(){},onOpen(){},onContinue(){},onAttentionOpen(){},onSeen(){},onSnooze(){},...patch});
const html=(component,props)=>renderToStaticMarkup(React.createElement(component,props));
function buttons(tree,result=[]){if(!React.isValidElement(tree))return result;if(tree.type==='button')result.push(tree);
  React.Children.forEach(tree.props.children,child=>buttons(child,result));return result;}

test('one entry is directly readable without an expansion step and multiple entries keep individual states',()=>{
  const props={group:group(),expanded:false,onExpand(){},onMore(){},stale:false,loading:false,children:e=>React.createElement(HomeEntryRow,{key:e.id,...rowProps({entry:e})})};
  const single=html(HomeEntryGroupCard,props);assert.match(single,/One logical task/);assert.doesNotMatch(single,/>Expand</);
  const multi=html(HomeEntryGroupCard,{...props,group:group({children:[entry(),entry({id:'entry2',title:'Idle context',kind:'session',display_state:'idle'})],children_total:2})});
  assert.match(multi,/One logical task/);assert.match(multi,/Idle context/);assert.match(multi,/No work in progress/);assert.match(multi,/>Expand</);
  assert.doesNotMatch(multi,/2 tasks|2 running/);
});

test('two exact sessions use separate targets without operation, latest or identity heuristics',()=>{
  const sessions=['session-one','session-two'].map(session_id=>({server_id:'server',executor_id:'executor',workspace_id:'ws',session_id}));
  const opened=[],tree=HomeEntryRow(rowProps({entry:entry({sessions,sessions_total:2}),onOpen:t=>opened.push(t)}));
  for(const button of buttons(tree))if(String(button.props.children).startsWith('View session'))button.props.onClick();
  assert.deepEqual(opened,sessions.map(ref=>({kind:'session',...ref})));assert.ok(opened.every(t=>!Object.hasOwn(t,'operation_id')));
});

test('related attention and result are nested in the same entry without a second work panel',()=>{
  const item=entry({attention_preview:[occurrence()],attention_total:1,attention_refs:['attention1'],results_total:1,result_refs:['result1'],result_tracking:'unknown',
    results_preview:[{id:'result1',title:'Canonical delivery',outcome:'SUCCEEDED',verification_state:null,cleanup_state:null,view_state:'not_tracked',workspace_id:'ws',agent_id:'A',preview:'<unsafe>',truncated:false,artifacts:[],attention:null,detail_target:target}]});
  const markup=html(HomeEntryRow,rowProps({entry:item}));assert.equal((markup.match(/data-home-entry="entry1"/g)||[]).length,1);
  assert.match(markup,/Related attention/);assert.match(markup,/Related results/);assert.match(markup,/viewing state partly untracked/);assert.match(markup,/&lt;unsafe&gt;/);
  assert.doesNotMatch(markup,/aria-label="Work"|aria-label="Results"|aria-label="Agents"/);
});

test('partial/unknown totals never activate quiet empty state or claim a first agent',()=>{
  assert.equal(isQuietEntries(page({items:[],total:0})),true);
  for(const patch of [{status:'partial'},{total:null},{total_is_exact:false},{source_status:{connections:'unavailable'}}])
    assert.equal(isQuietEntries(page({items:[],total:0,...patch})),false);
  assert.equal(isQuietEntries(page({items:[],total:0}),true),false);
});

test('viewing preference lookup requires canonical captured revisions and fresh current entry pages',()=>{
  const item=occurrence(),root=page({items:[group({children:[entry({attention_preview:[item]})]})]});
  const state={entries:root,entryChildren:{},entryAttention:{},entryResults:{},status:'ready',paused:false,loading:false,staleSections:[],hasPendingUpdate:false};
  assert.equal(freshHomeEntryOccurrence(state,item),item);
  for(const patch of [{paused:true},{hasPendingUpdate:true},{loading:true},{staleSections:['work']},{status:'forbidden'}])assert.equal(freshHomeEntryOccurrence({...state,...patch},item),undefined);
  assert.equal(freshHomeEntryOccurrence(state,{...item,seen_state:{...item.seen_state,revision:3}}),undefined);
  const ids=homeEntriesAnnouncementIds({...state,entries:page({items:[group({children:[entry({attention_refs:['attention1'],result_refs:['result1']})]})]})});
  assert.ok(ids.has('entry1')&&ids.has('attention1')&&ids.has('result1'));
});
