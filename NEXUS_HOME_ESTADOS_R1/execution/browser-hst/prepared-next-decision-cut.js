// PREPARED ONLY. Caller must first open the exact request through Home and bell
// in two own pages, with the canonical, unmodified fixtures' review forms ready.
// No invocation/allocation accompanies this file.
async page=>{
 const cfg=__CONFIG__;
 if(cfg.window!=='POST_PERF_BROWSER_WINDOW_OPEN')throw Error('Explicit Root window required');
 if(Date.parse(cfg.question_expires_at)-Date.now()<45000)throw Error('Insufficient original authority window; do not renew');
 const checks=[],posts=[],gets=[];let lost=null;
 const check=(id,ok,detail)=>{checks.push({id,ok,detail});if(!ok)throw Error(id);};
 const other=page.context().pages().find(p=>p!==page&&p.url()===cfg.other_url);
 if(!other)throw Error('Own second page must already be prepared through bell');
 const endpoint=cfg.url+'/api/v1/runtime-management/runtime/approval-decisions';
 const routeHandler=async route=>{
  if(route.request().method()!=='POST')return route.continue();
  // Never persist the request body/CAS/answer. Only opaque public intent IDs.
  const body=route.request().postDataJSON();
  check('posted-exact-original-request',body.approval_key.canonical_request_id===cfg.request_id,true);
  const first=posts.length===0;const log={client_intent_id:body.client_intent_id,status:null};posts.push(log);
  const response=await route.fetch();log.status=response.status();
  if(first){
   const raw=await response.json(),view=raw.data??raw;
   check('lost-response-was-canonically-accepted',[200,202].includes(response.status())&&!!view.decision_id,true);
   lost={decision_id:view.decision_id,native_operation_id:view.native_operation_id,client_intent_id:body.client_intent_id};
   await route.abort('failed');
  }else await route.fulfill({response});
 };
 for(const p of [page,other])p.on('request',r=>{if(r.method()==='GET')gets.push({path:new URL(r.url()).pathname});});
 await page.context().route(endpoint,routeHandler);
 try{
  for(const p of [page,other]){
   const form=p.getByRole('dialog');await form.getByLabel('Choose fixture output format',{exact:true}).selectOption(['0']);
   check('same-request-reviewed-'+(p===page?'home':'bell'),(await form.innerText()).includes(cfg.session_id),true);
  }
  await Promise.all([page,other].map(p=>p.getByRole('dialog').getByRole('button',{name:'Send answer',exact:true}).click()));
  for(let i=0;i<100&&!lost;i++)await page.waitForTimeout(50);
  check('one-response-deliberately-lost',!!lost,true);
  await page.getByRole('button',{name:'Check native decision',exact:true}).click();
  for(const p of [page,other])await p.getByTestId('canonical-native-status').waitFor({timeout:10000});
  const response=await page.request.get(endpoint+'/'+encodeURIComponent(lost.decision_id));const raw=await response.json(),view=raw.data??raw;
  check('same-receipt-recovered',response.status()===200&&view.decision_id===lost.decision_id&&view.native_operation_id===lost.native_operation_id,{decision_id:view.decision_id,native_operation_id:view.native_operation_id});
  check('recipient-and-session-unchanged',view.approval_key.canonical_request_id===cfg.request_id&&view.approval_key.session_id===cfg.session_id&&view.approval_key.workspace_id===cfg.workspace_id,true);
  check('no-productive-retry-on-recovery',posts.length<=2&&gets.some(x=>x.path.endsWith('/approval-decisions/'+lost.decision_id)),{posts,gets});
  check('second-view-reconciles-not-new-queue',await other.getByTestId('canonical-native-status').count()===1,true);
  return {status:'PREPARED_CUT_RESULT',checks,posts,receipt:lost,required_host_assertion:'Compare canonical pre/post rows: one decision and one native write for this request; exact recipient/tuple preserved; no grant/session/turn changes beyond the explicitly admitted decision',limits:['API fixture must snapshot authority tables before and after; browser alone cannot prove one durable effect','Lost canonical HTTP response is controlled transport, not naturally occurring failure','Must retain canonical conflict/current receipt from stale page; no fabricated success responses']};
 }catch(error){return {status:'FAIL_OR_INCOMPLETE',error:String(error),checks,posts,gets};}
 finally{await page.context().unroute(endpoint,routeHandler);}
}
