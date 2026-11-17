import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import ts from 'typescript';

// Execute the App's actual controlled Settings callback: the modal draft guard
// must refuse before either persistence or a displayed-Home state transition.
const source=ts.createSourceFile('App.tsx',readFileSync(new URL('../src/App.tsx',import.meta.url),'utf8'),ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);
let callback,initial;
const visit=node=>{
  if(ts.isJsxAttribute(node)&&node.name.getText(source)==='onHomeOperationalChange')callback=node.initializer.expression;
  if(ts.isVariableDeclaration(node)&&ts.isArrayBindingPattern(node.name)&&node.name.elements[0]?.name?.getText(source)==='homeOperational')initial=node.initializer.arguments[0];
  ts.forEachChild(node,visit);
};visit(source);
assert.ok(callback);assert.ok(initial);
const compile=expression=>ts.transpileModule('const value='+expression.getText(source),{compilerOptions:{target:ts.ScriptTarget.ES2022}}).outputText+';return value;';

test('Home display defaults off and preserves the exact existing opt-in value',()=>{
  for(const [value,expected] of [[null,false],['disabled',false],['true',false],['enabled',true]]){
    const read=new Function('localStorage',compile(initial))({getItem:key=>{assert.equal(key,'okto-nexus-home-operational');return value;}});
    assert.equal(read(),expected);
  }
});

test('Settings Home display callback honors an open draft guard before storage or state and uses no API',()=>{
  const writes=[],states=[];let allowed=false;
  const apply=new Function('mayLeavePanel','localStorage','setHomeOperational',compile(callback))(
    ()=>allowed,{setItem:(...args)=>writes.push(args)},next=>states.push(next));
  apply(true);assert.deepEqual(writes,[]);assert.deepEqual(states,[]);
  allowed=true;apply(true);apply(false);
  assert.deepEqual(writes,[['okto-nexus-home-operational','enabled'],['okto-nexus-home-operational','disabled']]);
  assert.deepEqual(states,[true,false]);
});
