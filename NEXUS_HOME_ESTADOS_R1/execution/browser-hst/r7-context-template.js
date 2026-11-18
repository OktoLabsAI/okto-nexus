async page=>{
 const cfg=__CONFIG__,checks=[],requests=[];const check=(id,ok,detail)=>{checks.push({id,ok,detail});if(!ok)throw Error(id);};
 page.on('request',r=>requests.push({method:r.method(),path:new URL(r.url()).pathname}));
 try{
  const response=await page.request.get(cfg.url+'/api/v1/home/harness-board?presentation_version=2&workspace_id='+cfg.workspace_id),board=(await response.json()).data;
  const card=board.columns.needs_you.items.find(x=>x.kind==='harness'&&x.id===cfg.card_id);
  check('stable-full-identity-after-terminal',card?.connection.server_id===cfg.reference.server_id&&card.connection.executor_id===cfg.reference.executor_id&&card.connection.binding_id===cfg.reference.binding_id&&card.connection.workspace_id===cfg.reference.workspace_id&&card.connection.workspace_binding_id===cfg.reference.workspace_binding_id&&card.connection.agent_id===cfg.reference.agent_id,card?.connection);
  const native=await page.request.get(cfg.url+'/api/v1/runtime-management/runtime/input-requests');const raw=await native.json();const data=raw.data??raw,rows=Array.isArray(data)?data:data.items;
  const pending=rows.find(x=>x.request_id===cfg.request_id||x.approval_id===cfg.request_id);const identity=pending?.request_payload?.kwargs?.approval_key;
  check('canonical-question-exact-session',identity?.session_id===cfg.session_a&&identity?.binding_id===cfg.reference.binding_id&&identity?.workspace_id===cfg.workspace_id,{session_id:identity?.session_id,binding_id:identity?.binding_id,workspace_id:identity?.workspace_id});
  const deliveries=board.columns.results.items.filter(x=>x.kind==='delivery');
  check('independent-terminal-result-exact-target',deliveries.some(x=>x.result?.detail_target?.session_id===cfg.session_b),deliveries.map(x=>({id:x.id,target:x.result?.detail_target,seen:x.result?.seen,semantics:x.result?.delivery_semantics})));
  await page.locator('[data-home-column="needs_you"]').getByRole('button',{name:'Respond',exact:true}).click();
  const dialog=page.getByRole('dialog',{name:'Activity detail'});await dialog.getByLabel('Choose fixture output format',{exact:true}).waitFor({timeout:10000});
  check('same-canonical-question-form-available',await page.getByRole('dialog').count()===1,true);
  await dialog.getByRole('button',{name:'Close modal',exact:true}).click();await dialog.waitFor({state:'hidden'});
  check('context-read-zero-post',requests.every(x=>x.method==='GET'),requests.filter(x=>x.method!=='GET'));
  return {status:'PASS_SUBSET',checks,requests,limits:['No decision or seen-preference mutation; result-unseen observation only','Question/parallel-session identities arise through canonical admissions and inert protocol peers']};
 }catch(error){return {status:'FAIL',error:String(error),checks,requests,body:await page.locator('body').innerText()};}
}
