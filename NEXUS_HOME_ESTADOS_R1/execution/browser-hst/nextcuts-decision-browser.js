async page=>{
 const cfg=__CONFIG__;
 if(cfg.window!=='POST_PERF_BROWSER_WINDOW_OPEN')throw Error('Explicit Root window required');
 const checks=[],posts=[],gets=[],errors=[];let ctx2=null,lost=null,firstDone;
 const firstReady=new Promise(resolve=>{firstDone=resolve;});
 const check=(id,ok,detail)=>{checks.push({id,ok,detail});if(!ok)throw Error(id);};
 const endpoint=cfg.url+'/api/v1/runtime-management/runtime/approval-decisions';
 const settings=({workspace})=>{localStorage.setItem('okto-nexus-home-operational','enabled');localStorage.setItem('okto-nexus-workspace',workspace);localStorage.setItem('okto-nexus:metrics-opt-in-prompt-dismissed:1.0.0',new Date().toISOString());};
 const handler=async route=>{
  if(route.request().method()!=='POST')return route.continue();
  const body=route.request().postDataJSON();
  const log={client_intent_id:body.client_intent_id,request_id:body.approval_key?.canonical_request_id,status:null};posts.push(log);
  if(log.request_id!==cfg.request_id){errors.push('foreign-request');firstDone(false);return route.abort();}
  const first=posts.length===1;
  if(!first)await firstReady;
  const response=await route.fetch();log.status=response.status();
  if(first){
   const raw=await response.json(),view=raw.data??raw;
   if(![200,202].includes(response.status())||!view.decision_id){errors.push('first-not-accepted');firstDone(false);return route.fulfill({response});}
   lost={decision_id:view.decision_id,native_operation_id:view.native_operation_id,client_intent_id:body.client_intent_id};
   firstDone(true);await route.abort('failed');
  }else{
   if([200,202].includes(response.status())){const raw=await response.json(),view=raw.data??raw;log.decision_id=view.decision_id;}
   await route.fulfill({response});
  }
 };
 try{
  check('original-question-window',Date.parse(cfg.question_expires_at)-Date.now()>45000,{expires_at:cfg.question_expires_at});
  const browser=page.context().browser();if(!browser)throw Error('Own browser cannot create second isolated context');
  ctx2=await browser.newContext({storageState:cfg.storage,viewport:{width:1440,height:1100}});
  await ctx2.addInitScript(settings,{workspace:cfg.workspace_id});const other=await ctx2.newPage();
  await page.addInitScript(settings,{workspace:cfg.workspace_id});await page.goto(cfg.url,{waitUntil:'domcontentloaded'});
  await other.goto(cfg.url,{waitUntil:'domcontentloaded'});
  for(const p of [page,other]){p.on('request',r=>{if(r.method()==='GET')gets.push({path:new URL(r.url()).pathname});});p.on('pageerror',e=>errors.push(String(e)));}
  await page.locator('[data-home-column="needs_you"]').getByRole('button',{name:'Respond',exact:true}).click();
  await other.getByTestId('global-attention-button').click();
  const bellRow=other.locator('[data-attention-id]').filter({has:other.getByTestId('attention-source-reference').filter({hasText:cfg.request_id})});
  await bellRow.waitFor({state:'visible',timeout:10000});
  check('bell-one-canonical-occurrence',await bellRow.count()===1,true);
  await bellRow.locator('button[data-testid^="attention-open-"]').click();
  for(const [name,p]of [['home',page],['bell',other]]){
   const section=p.getByRole('region',{name:'Native runtime decision'});
   // The component is a named section; use its visible content, never dump CAS.
   const dialog=p.getByRole('dialog');await dialog.getByLabel('Choose fixture output format',{exact:true}).waitFor({timeout:10000});
   check('exact-session-reviewed-'+name,(await dialog.innerText()).includes(cfg.session_id),cfg.session_id);
   await dialog.getByLabel('Choose fixture output format',{exact:true}).selectOption(['0']);
  }
  check('independent-contexts',page.context()!==other.context(),true);
  check('authority-before-submit',Date.parse(cfg.question_expires_at)-Date.now()>30000,true);
  await page.context().route(endpoint,handler);await ctx2.route(endpoint,handler);
  await Promise.all([page,other].map(p=>p.getByRole('dialog').getByRole('button',{name:'Send answer',exact:true}).click()));
  for(let i=0;i<150&&(!lost||posts.length<2||posts.some(p=>p.status===null));i++)await page.waitForTimeout(50);
  check('exactly-two-explicit-post-attempts',posts.length===2&&posts.every(p=>p.status!==null),posts);
  check('lost-real-acceptance-and-stale-conflict-or-receipt',!!lost&&[200,202].includes(posts[0].status)&&([409].includes(posts[1].status)||posts[1].decision_id===lost.decision_id),posts);
  const beforeRecovery=posts.length;
  for(const p of [page,other])await p.getByRole('button',{name:'Check native decision',exact:true}).click();
  for(const p of [page,other])await p.getByTestId('canonical-native-status').waitFor({timeout:10000});
  const response=await page.request.get(endpoint+'/'+encodeURIComponent(lost.decision_id)),raw=await response.json(),view=raw.data??raw;
  check('recover-same-decision-and-native-operation',response.status()===200&&view.decision_id===lost.decision_id&&view.native_operation_id===lost.native_operation_id,{decision_id:view.decision_id,native_operation_id:view.native_operation_id});
  check('exact-request-and-session-on-receipt',view.approval_key.canonical_request_id===cfg.request_id&&view.approval_key.session_id===cfg.session_id&&view.approval_key.workspace_id===cfg.workspace_id,true);
  const savedIntent=await page.evaluate(()=>Object.keys(sessionStorage).filter(k=>k.startsWith('okto-nexus:r4-native:')).map(k=>JSON.parse(sessionStorage.getItem(k)).client_intent_id));
  check('original-intent-preserved',savedIntent.includes(lost.client_intent_id),lost.client_intent_id);
  check('recovery-no-extra-post',posts.length===beforeRecovery&&gets.some(x=>x.path.endsWith('/approval-decisions/'+lost.decision_id)),{post_count:posts.length});
  check('honest-application-boundary',(await page.getByTestId('canonical-native-status').innerText()).includes('does not prove application'),true);
  check('no-page-exception',errors.length===0,errors);
  return {status:'PASS_BROWSER_SUBSET',checks,posts,receipt:lost,gets,expected_console:'One controlled lost POST response and possible canonical409; not page exceptions',limits:['Deterministic transport ordering holds stale second HTTP submission until first canonical acceptance; not a claim of simultaneous backend transaction scheduling','Host independently verifies exact durable decision/write/receipt counts','One inert protocol peer; no provider or causal resume acknowledgement']};
 }catch(error){return {status:'FAIL_OR_INCOMPLETE',error:String(error),checks,posts,gets,errors};}
 finally{firstDone(false);await page.context().unroute(endpoint,handler);if(ctx2){await ctx2.unroute(endpoint,handler);await ctx2.close();}}
}
