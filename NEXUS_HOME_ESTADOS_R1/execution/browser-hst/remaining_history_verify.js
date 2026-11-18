async page=>{
 const cfg=__CONFIG__,checks=[];if(cfg.window!=='REMAINING_FUNCTIONAL_WINDOW_OPEN')throw Error('Root review/window required');
 const check=(id,ok,detail)=>{checks.push({id,ok,detail});if(!ok)throw Error(id);};
 try{
  if(cfg.phase==='back'){
   await page.getByRole('dialog').waitFor({state:'hidden'});check('back-returns-to-home-without-target',!new URL(page.url()).searchParams.has('home_target'),true);
  }else{
   await page.getByRole('dialog',{name:'Activity detail'}).waitFor({timeout:10000});const actual=JSON.parse(new URL(page.url()).searchParams.get('home_target'));
   check(cfg.phase+'-same-complete-target',Object.keys(actual).length===Object.keys(cfg.target).length&&Object.entries(cfg.target).every(([k,v])=>actual[k]===v),actual);
   const response=await page.request.get(cfg.url+'/api/v1/runtime-management/runtime/sessions/'+encodeURIComponent(cfg.session_id)+'?executor_id='+encodeURIComponent(cfg.target.executor_id));const body=await response.json();
   check(cfg.phase+'-canonical-complete-preflight-scope',response.status()===200&&Object.entries(cfg.expected_scope).every(([k,v])=>body.scope?.[k]===v),{http_status:response.status(),scope:body.scope,lifecycle_state:body.lifecycle_state});
  }
  return {status:'PASS_SUBSET',checks,phase:cfg.phase};
 }catch(error){return {status:'FAIL_OR_INCOMPLETE',error:String(error),checks,phase:cfg.phase};}
}
