import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import ts from 'typescript';

// Execute the actual exported focus policy without loading dashboard effects,
// transport or a simulated app inventory. Browser qualification covers real DOM.
const source=ts.createSourceFile('App.tsx',readFileSync(new URL('../src/App.tsx',import.meta.url),'utf8'),ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);
const declaration=source.statements.find(node=>ts.isFunctionDeclaration(node)&&node.name?.text==='restoreClosedNavigationFocus');
assert.ok(declaration);
const module={exports:{}};
new Function('exports',ts.transpileModule(declaration.getText(source),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText)(module.exports);
const restore=module.exports.restoreClosedNavigationFocus;

test('closing navigation moves its own focus to the controlling trigger without scrolling',()=>{
  const calls=[],active={closest:()=>null},navigation={contains:value=>value===active};
  const trigger={focus:options=>calls.push(options)};
  assert.equal(restore(navigation,trigger,active),true);
  assert.deepEqual(calls,[{preventScroll:true}]);
});

test('closing navigation preserves legitimate outside/dialog focus and missing targets',()=>{
  const trigger={focus(){assert.fail('focus stolen');}};
  const outside={closest:()=>null},dialog={closest:()=>({role:'dialog'})};
  assert.equal(restore({contains:()=>false},trigger,outside),false);
  assert.equal(restore({contains:()=>true},trigger,dialog),false);
  assert.equal(restore(null,trigger,outside),false);
  assert.equal(restore({contains:()=>true},null,outside),false);
  assert.equal(restore({contains:()=>true},trigger,null),false);
});
