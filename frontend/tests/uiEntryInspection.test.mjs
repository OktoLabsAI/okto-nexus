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
const {initialEntrySession,initialHarnessSession,homeSessionTarget,homeSessionOptionLabel,assertHarnessSessionContext,assertEntryInspectionPage,entryInspectionQuery,occurrenceSession,readEntryInspectionPage}=load(new URL('../src/homeEntryInspection.ts',import.meta.url));
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
  assert.equal(initialEntrySession({...entry,sessions:[session('one')],sessions_total:1,has_more_sessions:true},target),null);
  assert.deepEqual(initialEntrySession({...entry,sessions:[session('one')],sessions_total:1},target),session('one'));
  assert.deepEqual(initialEntrySession(entry,{kind:'session',...session('two')}),session('two'));
  assert.deepEqual(initialEntrySession(entry,{kind:'execution',...session('two'),operation_id:'exact-op'}),session('two'));
});

test('harness direct selection requires full binding relation and strips display metadata from target',()=>{
  const ref={...session('one'),lifecycle_state:'READY',title:'Review API',workspace_label:'API',last_activity_at:'2026-11-17T12:00:00Z'};
  const c={connection:{server_id:'server',executor_id:'executor',workspace_id:'ws'},sessions:[ref],sessions_total:1,has_more_sessions:false,sessions_cursor:null};
  assert.equal(initialHarnessSession(c),ref);
  for(const patch of [{sessions_total:null},{has_more_sessions:true,sessions_cursor:'next'},{sessions:[ref,session('two')]},
    {sessions:[{...ref,lifecycle_state:undefined}]},{sessions:[{...ref,executor_id:'other'}]}])assert.equal(initialHarnessSession({...c,...patch}),null);
  assert.deepEqual(homeSessionTarget(ref),{kind:'session',...session('one')});
  const label=homeSessionOptionLabel(ref,0);assert.match(label,/Review API.*READY.*API.*Updated/);assert.doesNotMatch(label,/executor|one/);
});

test('one live session opens directly across closed history without choosing by recency',()=>{
  const live={...session('live'),lifecycle_state:'READY',last_activity_at:'2026-11-17T12:00:00Z'};
  const closed={...session('closed'),lifecycle_state:'CLOSED',last_activity_at:'2026-11-18T12:00:00Z'};
  const card={connection:session('unused'),sessions:[closed,live],sessions_total:2,has_more_sessions:false,sessions_cursor:null};
  assert.equal(initialHarnessSession(card),live);
  assert.equal(initialHarnessSession({...card,sessions:[live,closed]}),live);
  assert.equal(initialHarnessSession({...card,sessions:[closed],sessions_total:1}),closed);
  for(const patch of [
    {sessions:[live,{...closed,lifecycle_state:'READY'}]},
    {sessions:[live,{...closed,lifecycle_state:'OPEN_PENDING'}]},
    {sessions:[live,{...closed,session_id:live.session_id}]},
    {sessions:[live,{...closed,workspace_id:'other'}]},
    {sessions:[closed,{...closed,session_id:'other'}]},
    {sessions_total:3},{has_more_sessions:true},{sessions_cursor:'next'},
  ]) assert.equal(initialHarnessSession({...card,...patch}),null);
});

test('session viewer must revalidate full connection identity, including same-agent sibling binding',()=>{
  const connection={server_id:'server',executor_id:'executor',workspace_id:'ws',binding_id:'binding',workspace_binding_id:'wxb',agent_id:'agent'};
  const context={...connection,session_id:'one',lifecycle_state:'READY'};
  assert.doesNotThrow(()=>assertHarnessSessionContext(context,connection,session('one')));
  for(const patch of [{session_id:'two'},{binding_id:'other'},{workspace_binding_id:'other'},{executor_id:'other'},{agent_id:'other'}])
    assert.throws(()=>assertHarnessSessionContext({...context,...patch},connection,session('one')));
  assert.throws(()=>assertHarnessSessionContext(context,connection,{...session('one'),executor_id:'other'}));
});

test('relation conflict rereads first page once without changing exact selection or merging revisions',async()=>{
  const calls=[];const original=JSON.stringify(selection);
  const read=async cursor=>{calls.push(cursor);if(cursor)throw Object.assign(Error('changed'),{status:409});
    return {...page,revision:'new',items:[session('two')]};};
  const next=await readEntryInspectionPage(read,'old-cursor',selection,'server','sessions','rev');
  assert.deepEqual(calls,['old-cursor',null]);assert.equal(next.replaced,true);assert.equal(next.page.revision,'new');
  assert.deepEqual(next.page.items,[session('two')]);assert.equal(JSON.stringify(selection),original);
});

test('relation reads never retry forbidden/foreign scope or cross an aborted generation',async()=>{
  for(const scenario of ['forbidden','foreign','abort']){
    const abort=new AbortController();let calls=0;
    const read=async()=>{calls++;if(scenario==='forbidden')throw Object.assign(Error('denied'),{status:403});
      if(scenario==='abort')abort.abort();return {...page,server_id:scenario==='foreign'?'other':'server'};};
    await assert.rejects(()=>readEntryInspectionPage(read,'cursor',selection,'server','sessions','rev',abort.signal));
    assert.equal(calls,1);
  }
});

test('panel pagination rejects foreign parent, scope, revision and hidden default changes',()=>{
  assert.doesNotThrow(()=>assertEntryInspectionPage(page,selection,'server','sessions','rev'));
  for(const delta of [{server_id:'foreign'},{group_id:'other'},{entry_id:'other'},{partition:'results'},{revision:'changed'},
    {scope:{...page.scope,workspace_id:'other'}},{scope:{...page.scope,include_recent_results:false}},
    {scope:{...page.scope,agent_id:'other'}},{status:'unavailable'}])
    assert.throws(()=>assertEntryInspectionPage({...page,...delta},selection,'server','sessions','rev'));
});

test('related pages cannot cross negotiated presentation versions',()=>{
  const v2={...selection,presentationVersion:2};
  assert.throws(()=>assertEntryInspectionPage(page,v2,'server','sessions','rev'));
  assert.doesNotThrow(()=>assertEntryInspectionPage({...page,presentation_version:2},v2,'server','sessions','rev'));
  assert.throws(()=>assertEntryInspectionPage({...page,presentation_version:2},selection,'server','sessions','rev'));
  assert.equal('presentation_version'in entryInspectionQuery(selection,'v1'),false);
  assert.equal(entryInspectionQuery(v2,'v2').presentation_version,2);
  assert.equal(entryInspectionQuery(v2,null).cursor,undefined);
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
