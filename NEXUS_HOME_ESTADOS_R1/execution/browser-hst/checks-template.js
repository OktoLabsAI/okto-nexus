async page=>{
 const cfg=__CFG__,checks=[],requests=[],errors=[];
 const check=(name,ok,detail={})=>{checks.push({name,status:ok?'PASS':'FAIL',...detail});if(!ok)throw Error(name);};
 const api=async path=>{const response=await page.request.get(cfg.url+path,{headers:{'X-Nexus-UI':'1'}});
   check('HTTP '+path.split('?')[0],response.status()===200,{status:response.status()});const body=await response.json();return body.data??body;};
 page.on('pageerror',e=>errors.push(e.message));
 page.on('request',r=>requests.push({method:r.method(),path:new URL(r.url()).pathname}));
 try{
  const info=await api('/api/v1/info');check('v2 is advertised',info.home_presentation_versions?.includes(2));
  const query=new URLSearchParams({presentation_version:'2',workspace_id:cfg.workspace_id});
  const before=await api('/api/v1/home/harness-board?'+query);
  check('v2 authorized scope',before.presentation_version===2&&before.server_id===cfg.server_id&&before.scope.workspace_id===cfg.workspace_id);
  for(const column of ['active','needs_you','results']){
   const region=page.locator('[data-home-column="'+column+'"]');check(column+' exists',await region.count()===1);
   const ids=await region.locator('[data-home-harness],[data-home-signal]').evaluateAll(nodes=>nodes.map(n=>n.getAttribute('data-home-harness')??n.getAttribute('data-home-signal')));
   check(column+' exactly matches Server first page',JSON.stringify(ids)===JSON.stringify(before.columns[column].items.map(x=>x.id)),{ids});
  }
  check('one board and no category tabs',await page.locator('[data-testid="home-follow-up"]').count()===1&&await page.getByRole('tab').count()===0);
  // Expected facts come from the fixture contract, not inferred from UI text.
  const card=Object.values(before.columns).flatMap(c=>c.items).find(x=>x.id===cfg.card_id);
  check('fixture target exists',card?.kind==='harness');
  if(cfg.expected_activity)check('fixture canonical state',card.operational_status.activity===cfg.expected_activity);
  await page.screenshot({path:'output/playwright/home-states/desktop.png',fullPage:false});
  return {status:'PASS_SUBSET',checks,requests,errors,limits:['Only initial read/layout; pause/draft/mobile phases run separately.']};
 }catch(error){await page.screenshot({path:'output/playwright/home-states/failure.png',fullPage:false});return {status:'FAIL',message:error.message,checks,requests,errors};}
}
