async page=>{
 const cfg=__CONFIG__,checks=[];const check=(id,ok,detail)=>{checks.push({id,ok,detail});if(!ok)throw Error(id);};
 try{
  if(cfg.phase==='closed'){
   await page.getByRole('dialog').waitFor({state:'hidden'});check('back-closes-only-exact-detail',!new URL(page.url()).searchParams.has('home_target'),true);
  }else{
   const dialog=page.getByRole('dialog',{name:'Activity detail'});await dialog.waitFor({timeout:10000});
   const target=JSON.parse(new URL(page.url()).searchParams.get('home_target')),[server_id,executor_id,workspace_id,session_id]=JSON.parse(cfg.selected);
   check(cfg.phase+'-same-full-target',target.kind==='session'&&target.server_id===server_id&&target.executor_id===executor_id&&target.workspace_id===workspace_id&&target.session_id===session_id,{target});
   const response=await page.request.get(cfg.url+'/api/v1/runtime-management/runtime/sessions/'+encodeURIComponent(session_id)+'?executor_id='+encodeURIComponent(executor_id));const raw=await response.json(),data=raw.data??raw;
   check(cfg.phase+'-same-canonical-session',response.status()===200&&data.scope?.session_id===session_id&&data.scope?.executor_id===executor_id&&data.scope?.workspace_id===workspace_id,true);
  }
  return {status:'PASS_BROWSER_SUBSET',phase:cfg.phase,checks};
 }catch(error){return {status:'FAIL_OR_INCOMPLETE',error:String(error),phase:cfg.phase,checks};}
}
