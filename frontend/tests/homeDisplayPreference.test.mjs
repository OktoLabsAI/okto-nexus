import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import ts from 'typescript';

// Execute the App's actual controlled Settings callback: the modal draft guard
// must refuse before either persistence or a displayed-Home state transition.
const source=ts.createSourceFile('App.tsx',readFileSync(new URL('../src/App.tsx',import.meta.url),'utf8'),ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);
let callback,initial,projectCallback,completeCallback,resumeCallback,applyReturn;
const visit=node=>{
  if(ts.isJsxAttribute(node)&&node.name.getText(source)==='onHomeOperationalChange')callback=node.initializer.expression;
  if(ts.isJsxAttribute(node)&&node.name.getText(source)==='onComplete')completeCallback=node.initializer.expression;
  if(ts.isJsxAttribute(node)&&node.name.getText(source)==='onResume')resumeCallback=node.initializer.expression;
  if(ts.isVariableDeclaration(node)&&ts.isArrayBindingPattern(node.name)&&node.name.elements[0]?.name?.getText(source)==='homeOperational')initial=node.initializer.arguments[0];
  if(ts.isVariableDeclaration(node)&&node.name.getText(source)==='pickWorkspace')projectCallback=node.initializer;
  if(ts.isVariableDeclaration(node)&&node.name.getText(source)==='applyConnectionReturn')applyReturn=node.initializer;
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

test('both project selectors reuse the App scope callback with its draft guard and opaque IDs',()=>{
  assert.ok(projectCallback);
  const writes=[],states=[];let allowed=false;
  const choose=new Function('mayLeavePanel','localStorage','setWorkspace',compile(projectCallback))(
    ()=>allowed,{setItem:(...args)=>writes.push(args)},id=>states.push(id));
  choose('project/opaque:2');assert.deepEqual(writes,[]);assert.deepEqual(states,[]);
  allowed=true;choose('project/opaque:2');
  assert.deepEqual(writes,[['okto-nexus-workspace','project/opaque:2']]);
  assert.deepEqual(states,['project/opaque:2']);
});

test('completion defers its canonical project/context until the owning modal closes',()=>{
  assert.ok(completeCallback);
  for(const options of [undefined,{openContext:true},{openContext:false}]){
    const closed=[],pending=[];let tick=2,refreshes=0;
    const complete=new Function('setConnectFlowOpen','setRefreshTick','attention','setPendingConnectionReturn','identityKey',compile(completeCallback))(
      value=>closed.push(value),update=>{tick=update(tick);},{refresh:()=>refreshes++},next=>pending.push(next),'operator-identity');
    const binding={server_id:'server',executor_id:'executor',workspace_id:'project/opaque:2',binding_id:'binding',agent_id:'agent'};
    complete({binding},options);
    assert.deepEqual(closed,[false]);assert.equal(tick,3);assert.equal(refreshes,1);
    assert.deepEqual(pending,[{identityKey:'operator-identity',workspaceId:binding.workspace_id,openContext:options?.openContext!==false,target:{kind:'connection',...binding}}]);
  }
});

test('resume retains the exact binding and confirmed project for the deferred transition',()=>{
  assert.ok(resumeCallback);
  const closed=[],pending=[];
  const resume=new Function('setConnectFlowOpen','setPendingConnectionReturn','identityKey',compile(resumeCallback))(
    value=>closed.push(value),next=>pending.push(next),'operator-identity');
  const item={server_id:'server',executor_id:'executor',workspace_id:'another-project',binding_id:'specific-binding',agent_id:'same-agent'};
  resume(item);assert.deepEqual(closed,[false]);
  assert.deepEqual(pending,[{identityKey:'operator-identity',workspaceId:'another-project',openContext:true,target:{kind:'connection',...item}}]);
});

test('after modal unmount, a blocked project guard prevents scope, route and context changes',()=>{
  assert.ok(applyReturn);
  for(const allowed of [false,true])for(const openContext of [false,true]){
    const writes=[],scopes=[],targets=[],views=[],notices=[];
    const choose=new Function('mayLeavePanel','localStorage','setWorkspace',compile(projectCallback))(
      ()=>allowed,{setItem:(...args)=>writes.push(args)},id=>scopes.push(id));
    const apply=new Function('pickWorkspace','setWorkspaceNotice','setConnectionTarget','setView','identityKey',compile(applyReturn))(
      choose,text=>notices.push(text),target=>targets.push(target),view=>views.push(view),'operator-identity');
    const target={kind:'connection',server_id:'server',executor_id:'executor',workspace_id:'confirmed-project',binding_id:'binding',agent_id:'agent'};
    apply({identityKey:'operator-identity',workspaceId:'confirmed-project',openContext,target});
    assert.deepEqual(scopes,allowed?['confirmed-project']:[]);
    assert.deepEqual(writes,allowed?[['okto-nexus-workspace','confirmed-project']]:[]);
    assert.deepEqual(views,allowed&&!openContext?['Home']:[]);
    assert.deepEqual(targets,allowed&&openContext?[target]:[]);
    assert.equal(notices.length,allowed?0:1);
  }
});

test('a deferred return from an expired operator identity cannot change project or expose context',()=>{
  const refuse=()=>assert.fail('expired identity reached navigation');
  const apply=new Function('pickWorkspace','setWorkspaceNotice','setConnectionTarget','setView','identityKey',compile(applyReturn))(
    refuse,refuse,refuse,refuse,'new-operator');
  apply({identityKey:'previous-operator',workspaceId:'old-project',openContext:true,target:{kind:'connection'}});
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
