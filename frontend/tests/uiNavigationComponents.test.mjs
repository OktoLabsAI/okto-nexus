import assert from 'node:assert/strict';
import {existsSync, readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import test from 'node:test';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import ts from 'typescript';

// Same actual-source SSR approach as homeUI.test.mjs; no browser or network.
const require = createRequire(import.meta.url), modules = new Map();
function load(url) {
  const filename=fileURLToPath(url);
  if(modules.has(filename))return modules.get(filename).exports;
  const module={exports:{}};modules.set(filename,module);
  const code=ts.transpileModule(readFileSync(filename,'utf8'),{fileName:filename,compilerOptions:{
    module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText;
  const localRequire=name=>{
    if(!name.startsWith('.'))return require(name);
    const path=['.ts','.tsx','/index.ts'].map(ext=>new URL(name+ext,url)).find(p=>existsSync(p));
    assert.ok(path,name);return load(path);
  };
  new Function('require','module','exports',code)(localRequire,module,module.exports);return module.exports;
}
const {NavigationSidebar}=load(new URL('../src/components/NavigationSidebar.tsx',import.meta.url));
const {GlobalAttentionButton}=load(new URL('../src/components/GlobalAttentionButton.tsx',import.meta.url));
const html=(component,props)=>renderToStaticMarkup(React.createElement(component,props));
const state=(patch={})=>({page:null,summary:null,status:'loading',loading:false,loadingMore:false,pendingIds:[],error:null,notice:null,streamStatus:'off',...patch});
const summary=()=>({filters:{state:'active',seen:'all'},total:3,counts:{action_required:2,watch:1}});
function buttons(tree,result=[]) {
  if(!React.isValidElement(tree))return result;
  if(tree.type==='button')result.push(tree);
  React.Children.forEach(tree.props.children,child=>buttons(child,result));return result;
}

test('actual sidebar renders only four primary destinations plus Advanced, preserving legacy IDs and unread badge',()=>{
  const markup=html(NavigationSidebar,{view:'Home',unread:7,onNavigate(){}});
  assert.equal((markup.match(/<button/g)||[]).length,5);
  assert.deepEqual([...markup.matchAll(/data-view="([^"]+)"/g)].map(x=>x[1]),['Home','Meta-harness','Graph','Artifacts','Advanced']);
  assert.match(markup,/Conversations/);assert.match(markup,/unread-badge-Meta-harness/);
  assert.doesNotMatch(markup,/data-view="(?:Messages|Attention|Agents|Runtimes|Settings)"/);
});

test('nested advanced destination selects Advanced and navigation callbacks receive exact IDs',()=>{
  const calls=[],tree=NavigationSidebar({view:'Runtimes',unread:0,onNavigate:id=>calls.push(id)});
  const actual=buttons(tree);assert.equal(actual.filter(x=>x.props['aria-current']==='page').length,1);
  assert.equal(actual.find(x=>x.props['aria-current']==='page').props['data-view'],'Advanced');
  actual.find(x=>x.props['data-view']==='Meta-harness').props.onClick();assert.deepEqual(calls,['Meta-harness']);
  assert.doesNotMatch(html(NavigationSidebar,{view:'Runtimes',unread:0,onNavigate(){}}),/unread-badge/);
});

test('global bell displays active all-project counts and last-known stale state explicitly',()=>{
  const current=html(GlobalAttentionButton,{state:state({status:'ready',summary:summary()}),onOpen(){}});
  assert.match(current,/All projects and Server/);assert.match(current,/2 need action, 1 to watch/);
  assert.match(current,/data-testid="attention-badge"[^>]*>3<\/span>/);
  const stale=html(GlobalAttentionButton,{state:state({status:'stale',summary:summary()}),onOpen(){}});
  assert.match(stale,/Last known counts, out of date/);assert.match(stale,/>3\*<\/span>/);
});

test('global bell unknown/loading/forbidden/disabled never presents protected stale counts or false zero',()=>{
  for(const status of ['loading','error','forbidden','disabled']) {
    const markup=html(GlobalAttentionButton,{state:state({status,summary:summary(),error:'secret workspace payload'}),onOpen(){}});
    assert.doesNotMatch(markup,/secret workspace payload|>3\*?<\/span>|>0<\/span>|disabled=""/);
    assert.match(markup,/loading|unknown|disabled|cleared/);
  }
});

test('global bell rejects project/filter-specific counts and remains operable for disabled fallback',()=>{
  for(const filters of [{state:'active',seen:'all',workspace_id:'project-a'},{state:'resolved',seen:'all'},{state:'active',seen:'snoozed'}]) {
    const markup=html(GlobalAttentionButton,{state:state({status:'ready',summary:{...summary(),filters}}),onOpen(){}});
    assert.match(markup,/counts are unknown/);assert.doesNotMatch(markup,/>3<\/span>/);
  }
  let opens=0;const tree=GlobalAttentionButton({state:state({status:'disabled'}),onOpen(){opens++;}});
  assert.equal(tree.props.disabled,undefined);tree.props.onClick();assert.equal(opens,1);
});
