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
  const localRequire=name=>{if(!name.startsWith('.'))return require(name);const path=['.ts','.tsx'].map(ext=>new URL(name+ext,url)).find(p=>existsSync(p));assert.ok(path,name);return load(path);};
  new Function('require','module','exports',code)(localRequire,module,module.exports);return module.exports;
}
const {HomeProjectCard,HomeSummaryCards}=load(new URL('../src/components/home/HomeContextCards.tsx',import.meta.url));
const workspace={workspace_id:'project/opaque:2',display_name:'Chosen project',root_realpath:null};
const nodes=element=>React.isValidElement(element)?[element,...React.Children.toArray(element.props.children).flatMap(nodes)]:[];

test('Project card has one controlled selector and one resume action without changing identity',()=>{
  const selected=[],connections=[];
  const tree=HomeProjectCard({workspace:workspace.workspace_id,workspaces:[workspace],onChange:id=>selected.push(id),onConnect:()=>connections.push('explicit')});
  const all=nodes(tree),select=all.find(n=>n.type==='select'),button=all.find(n=>n.type==='button');
  assert.equal(select.props.value,workspace.workspace_id);
  select.props.onChange({currentTarget:{value:workspace.workspace_id}});
  button.props.onClick();assert.deepEqual(selected,[workspace.workspace_id]);assert.deepEqual(connections,['explicit']);
  const markup=renderToStaticMarkup(tree);
  assert.match(markup,/Chosen project/);assert.match(markup,/Choose a project/);
  assert.equal(all.filter(n=>n.type==='select').length,1);assert.equal(all.filter(n=>n.type==='button').length,1);
  const missing=renderToStaticMarkup(React.createElement(HomeProjectCard,{workspace:'retained-missing-id',workspaces:[workspace],onChange:()=>{},onConnect:()=>{}}));
  assert.match(missing,/value="retained-missing-id" selected="">Unavailable project/);
  assert.doesNotMatch(missing,/value="all" selected/);
});

test('overview cards render only supplied units and keep unknown/stale totals honest',()=>{
  const count=(value,unit,total_is_exact=true)=>({value,unit,total_is_exact});
  const summary={activities:count(12,'activities'),sessions:count(4,'sessions'),occurrences:count(null,'occurrences',false),results:count(3,'results',false),unseen_results:count(null,'results',false),external_instances:count(9,'external_instances')};
  const markup=renderToStaticMarkup(React.createElement(HomeSummaryCards,{summary,stale:true}));
  assert.match(markup,/Work/);assert.match(markup,/>12</);assert.match(markup,/Sessions/);assert.match(markup,/>4</);
  assert.match(markup,/Questions and updates/);assert.match(markup,/Not available/);assert.match(markup,/At least 3/);assert.match(markup,/Previous snapshot/);
  assert.doesNotMatch(markup,/executions|unseen|>9<|<ul|<select|<button/i);
});
