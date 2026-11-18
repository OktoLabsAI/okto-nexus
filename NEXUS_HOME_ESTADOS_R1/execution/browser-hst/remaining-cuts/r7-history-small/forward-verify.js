async page=>{
 const cfg={"window": "REMAINING_FUNCTIONAL_WINDOW_OPEN", "url": "http://127.0.0.1:54792", "workspace_id": "wsr_dda73f94f5c1e420832ed1b585f669d9", "session_id": "ses_dc635aa164da3d20c52455659ec4694e", "expected_scope": {"server_id": "srv_8be9b531fdf8dad9bbea648b68e99e8a", "executor_id": "exe_ba2298538700bb1325bd6f3172c17b44", "binding_id": "bind_839b0ab7231894ee410af30b18c71bc9", "agent_id": "hst-worker", "workspace_id": "wsr_dda73f94f5c1e420832ed1b585f669d9", "workspace_binding_id": "wxb_5077c5ed3ca82e45af39ee4e184cec61", "session_id": "ses_dc635aa164da3d20c52455659ec4694e", "session_owner_generation": 1, "authorization_revision": 2, "configuration_revision": 2, "binding_revision": 1, "credential_epoch": 1}, "target": {"executor_id": "exe_ba2298538700bb1325bd6f3172c17b44", "kind": "result", "operation_id": "op_e2cca372c7df6fedca20931c10017771", "server_id": "srv_8be9b531fdf8dad9bbea648b68e99e8a", "session_id": "ses_dc635aa164da3d20c52455659ec4694e", "workspace_id": "wsr_dda73f94f5c1e420832ed1b585f669d9"}, "delivery_id": "home_delivery_canonical:result_d2ebbe9a6dd144e9e6d38284404fe3884a9fd79e483cdec4f037ebaeed3bd784", "phase": "forward"},checks=[];if(cfg.window!=='REMAINING_FUNCTIONAL_WINDOW_OPEN')throw Error('Root review/window required');
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
