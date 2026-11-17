import assert from 'node:assert/strict';
import {existsSync,readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import test from 'node:test';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import ts from 'typescript';

const require=createRequire(import.meta.url),modules=new Map();
let observed;
function load(url){
  const filename=fileURLToPath(url);if(modules.has(filename))return modules.get(filename).exports;
  const module={exports:{}};modules.set(filename,module);
  const code=ts.transpileModule(readFileSync(filename,'utf8'),{fileName:filename,compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText;
  const localRequire=name=>{
    if(name.endsWith('/useHomeOverview'))return {useHomeOverview:()=>observed};
    if(name.endsWith('.css'))return {};if(!name.startsWith('.'))return require(name);
    const path=['.ts','.tsx','/index.ts'].map(ext=>new URL(name+ext,url)).find(p=>existsSync(p));assert.ok(path,name);return load(path);
  };
  new Function('require','module','exports',code)(localRequire,module,module.exports);return module.exports;
}
const {OperationalHome,isFirstHarnessEmpty}=load(new URL('../src/components/home/OperationalHome.tsx',import.meta.url));
const snapshot=(patch={})=>({version:1,partition:'groups',server_id:'server',status:'ready',items:[],total:0,total_is_exact:true,
  scope:{workspace_id:'ws',quick:'active',include_recent_results:true},has_more:false,next_cursor:null,
  source_status:{work:'ready',results:'ready',attention:'ready',connections:'ready',sessions:'ready',correlations:'ready',external:'ready'},
  inventory:{connections:{value:0,total_is_exact:true,unit:'connections'}},summary:{},coverage:{result_tracking:'ready'},
  server_attention:{status:'ready',total:0,items:[]},...patch});
const noop=()=>{};
function render(page,patch={}){
  const empty={items:[],total:0,total_is_exact:true,has_more:false,next_cursor:null};
  const board={...page,partition:'board',scope:{...page.scope,quick:'all',include_recent_results:false},entry_revision:page.revision??'entry-revision',
    columns:{active:{...empty,total:page.total,total_is_exact:page.total_is_exact},needs_you:{...empty},results:{...empty}}};
  observed={state:{entries:null,board,status:'ready',loading:false,paused:false,staleSections:[],hasPendingUpdate:false,entryLoading:null,boardLoading:null,
    generation:1,entryChildren:{},entrySessions:{},entryAttention:{},entryResults:{},...patch},
    refresh:noop,pause:noop,apply:noop,holdOrder:noop,loadEntries:noop,loadGroupChildren:noop,loadEntrySessions:noop,loadEntryAttention:noop,loadEntryResults:noop,loadBoardColumn:noop};
  return renderToStaticMarkup(React.createElement(OperationalHome,{workspace:'ws',workspaces:[],identityKey:'operator',refreshTick:0,
    latestEvent:null,streamStatus:'live',onNavigate:noop,onAttentionChanged:noop,onSetupAgent:noop,registerLeaveGuard:noop}));
}

test('first harness requires complete authorized pre-filter inventory, never an empty filtered result',()=>{
  assert.equal(isFirstHarnessEmpty(snapshot()),true);
  // A terminal/seen activity can disappear from the initial recent view while
  // its canonical connection still exists; entries.total0 alone is insufficient.
  assert.equal(isFirstHarnessEmpty(snapshot({inventory:{connections:{value:1,total_is_exact:true,unit:'connections'}}})),false);
  for(const patch of [{inventory:undefined},{inventory:{connections:{value:null,total_is_exact:false,unit:'connections'}}},
    {inventory:{connections:{value:0,total_is_exact:false,unit:'connections'}}},{status:'partial'},{status:'unavailable'},
    {total:null},{total_is_exact:false},{source_status:{connections:'unavailable'}},{source_status:{connections:'ready'}},
    {source_status:{work:'ready',results:'ready',attention:'ready',connections:'disabled',sessions:'ready',correlations:'ready',external:'ready'}},
    {scope:{workspace_id:'ws',quick:'needs_you',include_recent_results:false}},
    {scope:{workspace_id:'ws',quick:'active',include_recent_results:true,agent_id:'other'}}])
    assert.equal(isFirstHarnessEmpty(snapshot(patch)),false,JSON.stringify(patch));
  assert.equal(isFirstHarnessEmpty(snapshot(),true),false);
  assert.equal(isFirstHarnessEmpty(snapshot(),false,true),false);
});

test('actual Home presents one Connect or resume action and gates New request only for proved empty inventory',()=>{
  const empty=render(snapshot());
  assert.equal((empty.match(/<button[^>]*>Connect or resume<\/button>/g)||[]).length,1);
  assert.match(empty,/<button[^>]*disabled=""[^>]*>[\s\S]*?New request<\/button>/);
  assert.match(empty,/>Connect a collaborator<\/p>/);
  for(const page of [snapshot({inventory:undefined}),snapshot({inventory:{connections:{value:1,total_is_exact:true,unit:'connections'}}}),
    snapshot({status:'partial',total:null,total_is_exact:false}),snapshot({source_status:{connections:'unavailable'}})]){
    const markup=render(page);
    assert.doesNotMatch(markup,/>Connect a collaborator<\/p>/);
    assert.equal((markup.match(/<button[^>]*>Connect or resume<\/button>/g)||[]).length,1);
  }
  for(const patch of [{loading:true},{paused:true},{hasPendingUpdate:true},{staleSections:['entries']},{status:'stale'}])
    assert.doesNotMatch(render(snapshot(),patch),/>Connect a collaborator<\/p>/);
});
