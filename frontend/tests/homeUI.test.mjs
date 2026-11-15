import assert from 'node:assert/strict';
import {existsSync, readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import test from 'node:test';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import ts from 'typescript';

// Render the actual presentation, with no browser, service or network.
const require = createRequire(import.meta.url), modules = new Map();
function load(url) {
  const filename = fileURLToPath(url);
  if (modules.has(filename)) return modules.get(filename).exports;
  const module = {exports: {}};
  modules.set(filename, module);
  const compiled = ts.transpileModule(readFileSync(filename, 'utf8'), {fileName: filename, compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX,
  }}).outputText;
  const localRequire = name => {
    if (!name.startsWith('.')) return require(name);
    if (name.endsWith('.css')) return {};
    const path = ['.ts', '.tsx', '/index.ts'].map(extension => new URL(name + extension, url)).find(path => existsSync(path));
    assert.ok(path, name);
    return load(path);
  };
  new Function('require', 'module', 'exports', compiled)(localRequire, module, module.exports);
  return module.exports;
}

const {HomeCounters, HomeBlock, WorkRow, ResultRow, AttentionRow, downloadCurrentArtifact, isQuietHome, HomeWelcome} = load(new URL('../src/components/home/HomeCards.tsx', import.meta.url));
const {readContinuationContext, revalidateContinuation, clearHomeContinuationRequests} = load(new URL('../src/components/home/continuation.ts', import.meta.url));
const {RuntimeOperations} = load(new URL('../src/components/RuntimeOperations.tsx', import.meta.url));
const {MetaHarnessComposer} = load(new URL('../src/components/MetaHarnessComposer.tsx', import.meta.url));
const html = (component, props) => renderToStaticMarkup(React.createElement(component, props));
const target = {kind:'result',server_id:'server',workspace_id:'ws',executor_id:'exec',session_id:'session',operation_id:'op'};
const scope = {server_id:'server',workspace_id:'ws',executor_id:'exec',session_id:'session',agent_id:'agent',binding_id:'binding',workspace_binding_id:'wb'};
const session = () => ({scope:{...scope},lifecycle_state:'READY',control_available:true,durable_release_pending:false,lease_state:'ACTIVE',process_state:'RUNNING'});
const binding = () => ({agent_id:'agent',executor_id:'exec',workspace_id:'ws',binding_id:'binding',workspace_binding_id:'wb',adapter_id:'codex_app_server'});
const section = overrides => ({status:'ready',items:[],total:0,total_is_exact:true,has_more:false,next_cursor:null,as_of:null,next_refresh_at:null,...overrides});
function buttons(element, result=[]) {
  if (!React.isValidElement(element)) return result;
  if (element.type === 'button') result.push(element);
  React.Children.forEach(element.props.children, child => buttons(child,result));return result;
}
const work = overrides => ({id:'work1',kind:'direct_operation',source_ref:{type:'execution',id:'op',revision:1},workspace_id:'ws',title:'A task',title_origin:'canonical_title',agent_ids:['agent'],display_state:'native_accepted',state_since:null,last_activity_at:null,evidence_status:'confirmed',attention_refs:[],runtime_refs:[],detail_target:target,...overrides});
const result = overrides => ({id:'result1',source_ref:{type:'execution',id:'op',revision:1},workspace_id:'ws',agent_id:'agent',title:'Result',preview:'<script>not executable</script>',truncated:true,outcome:'SUCCEEDED',verification_state:'VERIFYING',cleanup_state:'PENDING',created_at:null,detail_target:target,artifacts:[],view_state:'not_tracked',attention:null,...overrides});

test('operational counters retain four units and unknown values', () => {
  const counter=(label,value,unit)=>({label,value,unit,total_is_exact:true});
  const markup=html(HomeCounters,{summary:{running:counter('Running',1,'activities'),waiting_start:counter('Waiting',2,'activities'),needs_you:counter('Needs you',3,'occurrences'),results:counter('Recent results',null,'results'),external:counter('External',9,'external_instances')}});
  assert.match(markup,/Not available/);assert.match(markup,/occurrences/);assert.doesNotMatch(markup,/9|total tasks/);
});
test('work keeps accepted distinct from running and stable activities for one agent', () => {
  const markup=renderToStaticMarkup(React.createElement('ul',null,[work({id:'one'}),work({id:'two',display_state:'running'})].map(item=>React.createElement(WorkRow,{key:item.id,item,onOpen(){}}))));
  assert.match(markup,/Accepted by runtime/);assert.match(markup,/Running/);assert.match(markup,/data-home-item="one"/);assert.match(markup,/data-home-item="two"/);assert.doesNotMatch(markup,/In this state since/);
});
test('work opens the exact target only on explicit click', () => {
  const calls=[],item=work();const tree=WorkRow({item,onOpen:value=>calls.push(value)});
  assert.equal(calls.length,0);buttons(tree)[0].props.onClick();assert.deepEqual(calls,[target]);
});
test('forbidden section cannot render protected children or an empty success', () => {
  const markup=html(HomeBlock,{title:'Work',section:section({status:'forbidden',total:null,items:[{}]}),empty:'Nothing to do',children:'PROTECTED'});
  assert.match(markup,/Total unknown/);assert.match(markup,/Access unavailable/);assert.doesNotMatch(markup,/PROTECTED|Nothing to do/);
});
test('partial sections disclose totals and load more inside the block', () => {
  let clicks=0;const props={title:'Work',section:section({status:'partial',total:8,total_is_exact:false,items:[{}],has_more:true}),empty:'No work',children:'one',onMore:()=>clicks++};
  assert.match(html(HomeBlock,props),/Partial information/);assert.match(html(HomeBlock,props),/At least 8/);
  const tree=HomeBlock(props);buttons(tree)[0].props.onClick();assert.equal(clicks,1);
});
test('result preview is escaped and outcome, cleanup and unseen tracking remain separate', () => {
  const markup=html(ResultRow,{item:result(),stale:false,onOpen(){},onSeen(){},onContinue(){}});
  assert.match(markup,/&lt;script&gt;/);assert.doesNotMatch(markup,/<script>/);assert.match(markup,/cleanup PENDING/);assert.match(markup,/seen state not tracked/);assert.match(markup,/Preview truncated/);
});
test('result opening never marks seen or silently continues', () => {
  const calls=[],tree=ResultRow({item:result(),stale:false,onOpen:t=>calls.push(['open',t]),onSeen:()=>calls.push(['seen']),onContinue:t=>calls.push(['continue',t])});
  assert.deepEqual(calls,[]);buttons(tree)[0].props.onClick();assert.deepEqual(calls,[['open',target]]);
  buttons(tree)[1].props.onClick();assert.deepEqual(calls[1],['continue',target]);
});
test('stale results disable preference and continuation controls', () => {
  const tree=ResultRow({item:result(),stale:true,onOpen(){},onSeen(){},onContinue(){}});
  assert.equal(buttons(tree).at(-1).props.disabled,true);
});
test('canonical continuation reads only the selected session and binding', async () => {
  const calls=[];const client={session:async(id,signal,executor)=>{calls.push(['session',id,executor]);return session();},binding:async id=>{calls.push(['binding',id]);return binding();}};
  const context=await readContinuationContext(client,target,'agent');assert.deepEqual(context.session.scope,scope);
  assert.deepEqual(calls,[['session','session','exec'],['binding','binding']]);
});
test('closed or draining continuation never looks up another session', async () => {
  for (const lifecycle_state of ['CLOSED','FAILED','CLOSING','DRAINING']) {
    let bindingReads=0;
    await assert.rejects(readContinuationContext({session:async()=>({...session(),lifecycle_state}),binding:async()=>{bindingReads++;return binding();}},target,'agent'),/exact session/);
    assert.equal(bindingReads,0);
  }
});
test('recipient and binding mismatch refuse rather than falling back', async () => {
  await assert.rejects(readContinuationContext({session:async()=>session(),binding:async()=>binding()},target,'other'),/exact result/);
  await assert.rejects(readContinuationContext({session:async()=>session(),binding:async()=>({...binding(),workspace_binding_id:'other'})},target,'agent'),/binding/);
  await assert.rejects(readContinuationContext({session:async()=>session(),binding:async()=>binding()},target,undefined),/recipient/);
});
test('revalidation compares every scope dimension before a continuation command', async () => {
  for (const field of Object.keys(scope)) await assert.rejects(revalidateContinuation({session:async()=>({...session(),scope:{...scope,[field]:'other'}})},scope),/exact session/);
  await assert.rejects(revalidateContinuation({session:async()=>({...session(),control_available:false})},scope),/exact session/);
});
test('real RuntimeOperations continuation presentation cannot select a new or recent session', () => {
  const markup=html(RuntimeOperations,{agentId:'agent',binding:binding(),canStart:false,continuationScope:scope});
  assert.match(markup,/Continue as operator in session session/);assert.match(markup,/Review runtime action/);
  assert.doesNotMatch(markup,/aria-label="Runtime action"|aria-label="Runtime session ID"|Reuse if unambiguous|Create a new session/);
});
test('shared composer exposes explicit message versus handoff without a hidden chosen recipient', () => {
  const markup=html(MetaHarnessComposer,{workspace:'ws',workspaces:[],agents:[],onSent(){}});
  assert.match(markup,/meta-kind-message/);assert.match(markup,/meta-kind-handoff/);assert.match(markup,/choose agent/);
  assert.match(markup,/<button[^>]*disabled=""[^>]*aria-label="Send turn"/);
});

test('logout clears only Home continuation content and leaves unrelated recovery records intact', () => {
  const home='okto-nexus:r4-runtime:'+JSON.stringify(['server','operator','agent','binding','home-continuation','session','wb']);
  const unrelated='okto-nexus:r4-runtime:'+JSON.stringify(['server','operator','agent','binding','wb']);
  const keys=new Map([[home,'sensitive reviewed message'],[unrelated,'legacy record'],['settings','value']]);
  const storage={get length(){return keys.size;},key:i=>[...keys.keys()][i]??null,removeItem:key=>keys.delete(key)};
  clearHomeContinuationRequests(storage);
  assert.equal(keys.has(home),false);assert.equal(keys.get(unrelated),'legacy record');assert.equal(keys.get('settings'),'value');
});


test('late artifact content is never downloaded after access or mount invalidation', async () => {
  let resolve, active=true, downloads=0;
  const pending=downloadCurrentArtifact(() => new Promise(done=>{resolve=done;}),()=>active,()=>downloads++);
  active=false;resolve(new Blob(['old authorized content']));
  assert.equal(await pending,false);assert.equal(downloads,0);
  assert.equal(await downloadCurrentArtifact(async()=>new Blob(['current']),()=>true,()=>downloads++),true);
  assert.equal(downloads,1);
});


test('quiet Home requires confirmed empty sources and never hides partial or unknown work', () => {
  const snapshot={work:section({}),results:section({}),attention:section({}),external_activity:section({status:'disabled'}),agents:section({})};
  assert.equal(isQuietHome(snapshot),true);
  assert.equal(isQuietHome({...snapshot,agents:section({total:1,items:[{agent_id:'worker'}]})}),true);
  for (const key of ['work','results','attention','agents']) {
    for (const status of ['partial','unavailable','forbidden','disabled'])
      assert.equal(isQuietHome({...snapshot,[key]:section({status})}),false);
  }
  assert.equal(isQuietHome({...snapshot,work:section({total:null})}),false);
  assert.equal(isQuietHome({...snapshot,work:section({total_is_exact:false})}),false);
  assert.equal(isQuietHome({...snapshot,external_activity:section({status:'unavailable'})}),false);
  assert.equal(isQuietHome({...snapshot,work:section({items:[work({})],total:1})}),false);
  assert.equal(isQuietHome(snapshot,true),false);
});

test('quiet welcome reuses explicit onboarding or request callback, with disabled observations disclosed', () => {
  let setup=0,request=0;
  const props={needsSetup:true,externalDisabled:true,onSetup:()=>setup++,onRequest:()=>request++};
  const markup=html(HomeWelcome,props);
  assert.match(markup,/Set up your first agent/);assert.match(markup,/External reports are disabled/);
  assert.doesNotMatch(markup,/Operational summary/);
  buttons(HomeWelcome(props))[0].props.onClick();assert.deepEqual([setup,request],[1,0]);
  buttons(HomeWelcome({...props,needsSetup:false}))[0].props.onClick();assert.deepEqual([setup,request],[1,1]);
});
