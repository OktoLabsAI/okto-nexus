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
const {HomeHarnessCard,HomeHarnessSignalCard,harnessEventAction}=load(new URL('../src/components/home/HomeHarnessCard.tsx',import.meta.url));
const target={kind:'result',server_id:'private-server',executor_id:'private-executor',workspace_id:'private-project',session_id:'private-session',operation_id:'private-operation'};
const event={id:'event',kind:'result',entry_id:'private-entry',group_id:'original-group',entry_revision:'entry-revision',target,title:'Report delivered',display_state:'succeeded',evidence:'confirmed',occurred_at:null};
const card={kind:'harness',id:'card',connection:{agent_label:'Research collaborator',harness_id:'codex_app_server',host_label:'Team computer'},context_state:'registered',activity_state:'registered',blocks_harness:false,reminder_snoozed:false,
  blocking_requests:[],reconnect_reason:'Individual reconnection is not available for this host.',
  children:[],children_total:40,events_preview:[event],events_total:40,has_more_events:true,events_summary:{attention:0,results:12,work:28,sessions:0,external:0}};
const render=(value=card)=>renderToStaticMarkup(React.createElement(HomeHarnessCard,{card:value,column:'active',blocked:false,onActivity(){},onEvent(){}}));
test('registered harness preview uses friendly identity and Server events, without technical expansion or onboarding',()=>{
  const html=render();
  assert.match(html,/Research collaborator/);assert.match(html,/Codex/);assert.doesNotMatch(html,/Team computer/);assert.match(html,/Registered harness/);
  assert.match(html,/Report delivered/);assert.match(html,/View delivery/);assert.match(html,/Open console/);
  assert.doesNotMatch(html,/<button[^>]*>Reconnect|12 results|Connection details|Individual reconnection/);
  assert.doesNotMatch(html,/private-server|private-executor|private-session|private-operation|original-group|Related attention|Related results|Connect or resume|Continue/);
  assert.doesNotMatch(html,/40.*sessions|0 sessions|Running|Ready to execute/);
});
test('work previews retain authorized subjects and omit the generic label for a direct turn',()=>{
  const turn={...event,kind:'work',target:{...target,kind:'execution'},title:'Work request',display_state:'running'};
  const named={...turn,id:'named',target:{kind:'handoff'},title:'Review storefront accessibility'};
  const delivered={...event,id:'delivered',title:turn.title,entry:turn};
  const html=render({...card,events_preview:[turn,named,delivered]});
  assert.match(html,/Running/);
  assert.doesNotMatch(html,/View work/);
  assert.equal((html.match(/>Open console<\/button>/g)??[]).length,1);
  assert.match(html,/Review storefront accessibility/);
  assert.doesNotMatch(html,/Work request|private-session/);
});
test('delivery shows local received time while retaining the machine-readable timestamp',()=>{
  const timestamp='2026-11-18T02:27:29.773Z';
  const item={kind:'delivery',id:'delivery',result:{title:'Storefront review',created_at:timestamp},harness_refs:[]};
  const html=renderToStaticMarkup(React.createElement(HomeHarnessSignalCard,{item,blocked:false,onOpen(){}}));
  const local=new Intl.DateTimeFormat('en-US',{month:'short',day:'2-digit',hour:'2-digit',minute:'2-digit'}).format(new Date(timestamp));
  assert.ok(html.includes(`Received <time dateTime="${timestamp}">${local}</time>`),html);
});
test('question/approval affordance respects canonical allowed actions and preserves exact event target on click',()=>{
  assert.equal(harnessEventAction({...event,kind:'attention',attention:{allowed_actions:['respond_native'],resolution:'open',freshness:'current'}}),'Review question');
  assert.equal(harnessEventAction({...event,kind:'attention',attention:{allowed_actions:['decide_native'],resolution:'open',freshness:'current'}}),'Review approval');
  assert.equal(harnessEventAction({...event,kind:'attention',attention:{allowed_actions:['inspect_approval']}}),'Review update');
  let opened=null,activity=0;
  const tree=HomeHarnessCard({card,column:'active',blocked:false,onActivity(){activity++;},onEvent(value){opened=value;}});
  const buttons=[];const walk=node=>{if(!node||typeof node!=='object')return;if(node.type==='button')buttons.push(node);React.Children.forEach(node.props?.children,walk);};walk(tree);
  buttons.find(node=>node.props.children==='View delivery').props.onClick();
  assert.equal(opened,event);assert.equal(opened.target,target);assert.equal(opened.group_id,'original-group');assert.equal(activity,0);
  buttons.find(node=>node.props.children==='Open console').props.onClick();assert.equal(activity,1);
});
test('unknown identity and tracking remain explicit without IDs as friendly-name fallbacks',()=>{
  const html=render({...card,connection:{...card.connection,agent_label:null,host_label:null,agent_id:'private-agent'},events_summary:{attention:null,results:0,work:0,sessions:0,external:0}});
  assert.match(html,/<h4[^>]*>Codex/);assert.doesNotMatch(html,/Host not reported|Activity coverage incomplete|private-agent|0 results/);
});
test('independent request identifies its harness and never infers blocked or running from a missing proof',()=>{
  const item={kind:'request',id:'notification',request:{kind:'native_question_pending',allowed_actions:['respond_native'],freshness:'current',resolution:'open'},
    harness_refs:[{card_id:'private-card',connection:card.connection}],blocks_harness:null};
  const html=renderToStaticMarkup(React.createElement(HomeHarnessSignalCard,{item,blocked:false,onOpen(){}}));
  assert.match(html,/Research collaborator/);assert.match(html,/Codex/);assert.doesNotMatch(html,/Team computer/);assert.match(html,/Blocking status unconfirmed/);assert.match(html,/Respond/);
  assert.doesNotMatch(html,/private-card|Running|Waiting for your response|Continue|Reconnect/);
});
test('reported completion without native result remains a report, and waiting confirmation/snooze never imply resumed work',()=>{
  const item={kind:'delivery',id:'reported',result:null,report:{kind:'external_completion_unseen',allowed_actions:['inspect_external_observation']},
    harness_refs:[{card_id:'private-card',connection:card.connection}],completion_evidence:'reported'};
  const html=renderToStaticMarkup(React.createElement(HomeHarnessSignalCard,{item,blocked:false,onOpen(){}}));
  assert.match(html,/Completion reported/);assert.match(html,/View result/);assert.match(html,/Not verified by Nexus/);assert.doesNotMatch(html,/SUCCEEDED|native success|Outcome:|Continue/);
  const waiting=render({...card,activity_state:'awaiting_confirmation',reminder_snoozed:true,blocks_harness:null});
  assert.match(waiting,/Waiting for confirmation/);assert.match(waiting,/does not resume the harness/);assert.doesNotMatch(waiting,/>Working</);
});
test('Active references a nonblocking question without duplicating its Needs you action; blocked harness keeps its action inside',()=>{
  const question={...event,kind:'attention',title:'Choose the report format',attention:{kind:'native_question_pending',allowed_actions:['respond_native'],resolution:'open',freshness:'current'}};
  const value={...card,events_preview:[question],events_summary:{attention:1,results:0,work:0,sessions:0,external:0}};
  const active=render(value);assert.match(active,/Choose the report format/);assert.match(active,/Open console/);assert.doesNotMatch(active,/Review question/);
  const waiting=renderToStaticMarkup(React.createElement(HomeHarnessCard,{card:{...value,activity_state:'waiting_for_user',blocks_harness:true},column:'needs_you',blocked:false,onActivity(){},onEvent(){}}));
  assert.match(waiting,/Choose the report format/);assert.match(waiting,/Review question/);assert.match(waiting,/View context/);assert.doesNotMatch(waiting,/Reconnect/);
});
test('actual overview signal handler opens the exact canonical attention when its entry has no target',()=>{
  const filename=fileURLToPath(new URL('../src/components/home/OperationalHome.tsx',import.meta.url));
  const source=ts.createSourceFile(filename,readFileSync(filename,'utf8'),ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);
  let handler,requestHelper;
  const visit=node=>{if(ts.isVariableDeclaration(node)&&node.name.getText(source)==='requestPanel')requestHelper=node.initializer;
    if(ts.isJsxSelfClosingElement(node)&&node.tagName.getText(source)==='HomeHarnessSignalCard'){
    handler=node.attributes.properties.find(prop=>prop.name?.getText(source)==='onOpen')?.initializer?.expression;
  }ts.forEachChild(node,visit);};visit(source);assert.ok(handler);assert.ok(requestHelper);
  const compiled=ts.transpileModule(`const requestPanel=(${requestHelper.getText(source)});module.exports=(${handler.getText(source)});`,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
  const {primaryAttentionAction}=load(new URL('../src/attentionPresentation.ts',import.meta.url));
  const invoke=card=>{
    const calls=[],module={exports:null};
    new Function('card','open','selectEntry','primaryAttentionAction','module',compiled)(card,value=>calls.push(value),()=>assert.fail('No entry target may be invented'),primaryAttentionAction,module);
    module.exports();return calls;
  };
  const request={attention_id:'exact-question',kind:'native_question_pending',allowed_actions:['respond_native'],freshness:'current',resolution:'open',source_revision:'q7'};
  const [opened]=invoke({kind:'request',entry:{target:null},request,harness_refs:[]});
  assert.equal(opened.kind,'attention');assert.equal(opened.item,request);assert.equal(opened.action,'respond_native');
  const report={attention_id:'exact-report',kind:'external_completion_unseen',source_type:'external_observation',allowed_actions:['inspect_external_observation'],source_revision:'r3'};
  const [external]=invoke({kind:'delivery',entry:{target:null},result:null,report,harness_refs:[]});
  assert.equal(external.kind,'attention');assert.equal(external.item,report);assert.equal(external.action,'inspect_external_observation');
});
test('Home displays the collaborator and adapter without exposing connection IDs',()=>{
  const value={...card,connection:{...card.connection,connect_id:'reviewer'}};
  const html=render(value);assert.doesNotMatch(html,/Harness ID|reviewer/);assert.match(html,/Research collaborator/);assert.match(html,/Codex/);
  assert.equal(value.connection.harness_id,'codex_app_server');assert.equal(value.events_preview[0].target,target);
  const signal={kind:'request',id:'request',request:{kind:'native_question_pending',allowed_actions:['respond_native'],freshness:'current',resolution:'open'},
    harness_refs:[{card_id:'card',connection:value.connection}],blocks_harness:false};
  const request=renderToStaticMarkup(React.createElement(HomeHarnessSignalCard,{item:signal,blocked:false,onOpen(){}}));
  assert.doesNotMatch(request,/Harness ID|reviewer/);assert.match(request,/Codex/);assert.match(request,/Respond/);
  assert.doesNotMatch(render(),/Harness ID/);
});

const count=value=>({value,total_is_exact:value!==null});
const operational=patch=>({version:1,connection:'connected',activity:'waiting_user',blocking:'full',freshness:'current',as_of:null,state_since:null,reason_code:null,
  pending_actions:count(1),pending_by_kind:{question:count(1),approval:count(0),decision:count(0),verification:count(0)},
  pending_request_ids:['exact-question'],has_more_pending_requests:false,pending_requests_cursor:null,running_sessions:count(0),blocked_sessions:count(1),awaiting_native_confirmation:false,...patch});
const questionRequest={kind:'request',id:'request',request:{attention_id:'exact-question',source_revision:'q7',kind:'native_question_pending',allowed_actions:['respond_native'],resolution:'open',freshness:'current'},
  harness_refs:[],entry:{workspace_id:'project'},blocks_session:true,blocks_harness:true};
const buttonsOf=tree=>{const out=[];const visit=node=>{if(!node||typeof node!=='object')return;if(node.type==='button')out.push(node);React.Children.forEach(node.props?.children,visit);};visit(tree);return out;};
test('v2 one exact open action opens its canonical request only once and shows project',()=>{
  const selected=[],value={...card,connection:{...card.connection,workspace_id:'project',workspace_label:'API'},placement_reason:'human_block_confirmed',operational_status:operational(),
    requests_preview:[questionRequest],events_preview:[{...event,kind:'attention',attention:questionRequest.request}]};
  const tree=HomeHarnessCard({card:value,column:'needs_you',blocked:false,showProject:true,onActivity(){assert.fail('No intermediary selection needed');},onEvent(){assert.fail('No duplicate event action');},onRequest:r=>selected.push(r)});
  const buttons=buttonsOf(tree);assert.equal(buttons.length,1);assert.equal(buttons[0].props.children,'Respond');buttons[0].props.onClick();
  assert.equal(selected[0],questionRequest);assert.equal(selected[0].request.source_revision,'q7');
  const html=renderToStaticMarkup(tree);assert.match(html,/>API</);assert.match(html,/Waiting for your response/);assert.doesNotMatch(html,/Reconnect|>Working</);
});
test('partial singleton preview and multiple actions require the complete contextual action list',()=>{
  for(const patch of [{pending_actions:{value:1,total_is_exact:false}},{has_more_pending_requests:true,pending_requests_cursor:'cursor'},{pending_actions:count(7)}]){
    let opened=0;
    const tree=HomeHarnessCard({card:{...card,placement_reason:'human_block_confirmed',operational_status:operational(patch),requests_preview:[questionRequest]},column:'needs_you',blocked:false,
      onActivity(){assert.fail('Use the action relation');},onEvent(){},onRequest(){assert.fail('Preview does not prove singleton');},onRequests(){opened++;}});
    const button=buttonsOf(tree).at(-1);assert.notEqual(button.props.children,'Respond');button.props.onClick();assert.equal(opened,1);
  }
});
test('recorded decision follows confirmation and never offers Respond again',()=>{
  const value={...card,placement_reason:'awaiting_native_confirmation',operational_status:operational({activity:'awaiting_confirmation',blocking:'unknown',pending_actions:count(0),awaiting_native_confirmation:true}),requests_preview:[]};
  const html=renderToStaticMarkup(React.createElement(HomeHarnessCard,{card:value,column:'needs_you',blocked:false,onActivity(){},onEvent(){}}));
  assert.match(html,/Waiting for resume confirmation/);assert.match(html,/No further response is required/);assert.match(html,/Follow confirmation/);assert.doesNotMatch(html,/>Respond<|>Working</);
});
test('stale Idle is explicitly last known and does not disable exact read by itself',()=>{
  const tree=HomeHarnessCard({card:{...card,operational_status:operational({activity:'idle',blocking:'none'})},column:'active',blocked:false,stale:true,onActivity(){},onEvent(){}});
  assert.match(renderToStaticMarkup(tree),/Last known: Idle/);assert.equal(buttonsOf(tree).at(-1).props.disabled,false);
});
