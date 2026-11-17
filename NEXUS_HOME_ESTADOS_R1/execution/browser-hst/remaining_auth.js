async page=>{
 const cfg=__CONFIG__,checks=[],denials=[];const check=(id,ok,detail)=>{checks.push({id,ok,detail});if(!ok)throw Error(id);};
 if(cfg.window!=='REMAINING_FUNCTIONAL_WINDOW_OPEN')throw Error('Root review/window required');
 page.on('response',r=>{if([401,403].includes(r.status()))denials.push({path:new URL(r.url()).pathname,status:r.status()});});
 try{
  const response=await page.request.get(cfg.url+'/api/v1/home/harness-board?presentation_version=2&workspace_id='+cfg.workspace_id);check('real-own-session-revoked',[401,403].includes(response.status()),response.status());
  // Real canonical decision-detail polling is2.5s. Do not forge its response,
  // dispatch auth events, click Apply or dismiss a dirty form to force cleanup.
  for(let i=0;i<100;i++){if(await page.getByRole('dialog').count()===0&&await page.locator('[data-home-harness]').count()===0)break;await page.waitForTimeout(100);}
  check('logout-clears-dirty-protected-panel',await page.getByRole('dialog').count()===0&&await page.getByLabel('Choose fixture output format',{exact:true}).count()===0&&await page.locator('[data-home-harness]').count()===0,true);
  check('canonical-ui-denial-observed',denials.length>0,denials);
  return {status:'PASS_SUBSET',checks,denials};
 }catch(error){return {status:'FAIL_OR_INCOMPLETE',error:String(error),checks,denials};}
}
