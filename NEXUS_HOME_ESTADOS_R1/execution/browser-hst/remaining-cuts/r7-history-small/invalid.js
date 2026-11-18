async page=>{
 const cfg={"window": "REMAINING_FUNCTIONAL_WINDOW_OPEN", "url": "http://127.0.0.1:54792", "workspace_id": "wsr_dda73f94f5c1e420832ed1b585f669d9", "session_id": "ses_dc635aa164da3d20c52455659ec4694e", "expected_scope": {"server_id": "srv_8be9b531fdf8dad9bbea648b68e99e8a", "executor_id": "exe_ba2298538700bb1325bd6f3172c17b44", "binding_id": "bind_839b0ab7231894ee410af30b18c71bc9", "agent_id": "hst-worker", "workspace_id": "wsr_dda73f94f5c1e420832ed1b585f669d9", "workspace_binding_id": "wxb_5077c5ed3ca82e45af39ee4e184cec61", "session_id": "ses_dc635aa164da3d20c52455659ec4694e", "session_owner_generation": 1, "authorization_revision": 2, "configuration_revision": 2, "binding_revision": 1, "credential_epoch": 1}, "target": {"executor_id": "exe_ba2298538700bb1325bd6f3172c17b44", "kind": "result", "operation_id": "op_e2cca372c7df6fedca20931c10017771", "server_id": "srv_8be9b531fdf8dad9bbea648b68e99e8a", "session_id": "ses_dc635aa164da3d20c52455659ec4694e", "workspace_id": "wsr_dda73f94f5c1e420832ed1b585f669d9"}, "delivery_id": "home_delivery_canonical:result_d2ebbe9a6dd144e9e6d38284404fe3884a9fd79e483cdec4f037ebaeed3bd784", "selected": "[\"srv_8be9b531fdf8dad9bbea648b68e99e8a\", \"exe_ba2298538700bb1325bd6f3172c17b44\", \"wsr_dda73f94f5c1e420832ed1b585f669d9\", \"ses_dc635aa164da3d20c52455659ec4694e\"]"},checks=[],requests=[];let bad=null;const check=(id,ok,detail)=>{checks.push({id,ok,detail});if(!ok)throw Error(id);};
 try{
  const [server_id,executor_id,workspace_id]=JSON.parse(cfg.selected),target={kind:'session',server_id,executor_id,workspace_id,session_id:'hst-not-a-canonical-session'};
  const url=new URL(cfg.url);url.searchParams.set('home_target',JSON.stringify(target));bad=await page.context().newPage();bad.on('request',r=>requests.push({method:r.method(),path:new URL(r.url()).pathname}));
  const denied=bad.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/home/target'&&[403,404].includes(r.status()),{timeout:10000});
  await bad.goto(url.toString(),{waitUntil:'domcontentloaded'});const response=await denied;await bad.waitForTimeout(500);
  check('invalid-reference-denied',response.status()===403||response.status()===404,response.status());
  check('invalid-reference-never-reads-latest-session',requests.filter(x=>x.path.includes('/runtime/sessions/')).every(x=>x.path.includes(target.session_id)),requests.filter(x=>x.path.includes('/runtime/sessions/')));
  check('invalid-reference-zero-write',requests.every(x=>x.method==='GET'),true);
  return {status:'PASS_BROWSER_SUBSET',checks,requests,limits:['Missing exact reference, not foreign-principal preview/counter audit']};
 }catch(error){return {status:'FAIL_OR_INCOMPLETE',error:String(error),checks,requests};}
 finally{if(bad)await bad.close();}
}
