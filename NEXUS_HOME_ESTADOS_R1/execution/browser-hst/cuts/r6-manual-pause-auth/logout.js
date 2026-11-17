async page=>{
 const cfg={"url": "http://127.0.0.1:54940", "workspace_id": "wsr_2b7ed01054e310acd6663d074217840c"},checks=[];
 const check=(id,ok,detail)=>{checks.push({id,ok,detail});if(!ok)throw Error(id);};
 try{
  const r=await page.request.get(cfg.url+'/api/v1/home/harness-board?presentation_version=2&workspace_id='+cfg.workspace_id);
  check('canonical-revocation-denies-read',[401,403].includes(r.status()),r.status());
  const refresh=page.getByRole('button',{name:'Refresh',exact:true});
  if(await refresh.count())await refresh.click();
  await page.waitForTimeout(1500);
  const body=await page.locator('body').innerText();
  check('protected-board-cleared',await page.getByTestId('home-board').count()===0&&!(await page.locator('[data-home-harness]').count()),body);
  check('fixture-data-cleared',!body.includes('Hst Worker')&&!body.includes('HST synthetic output'),true);
  return {status:'PASS_SUBSET',checks,body,http_status:r.status(),revocation:'Real own-account logout; not intercepted status'};
 }catch(error){return {status:'FAIL',error:String(error),checks,body:await page.locator('body').innerText()};}
}
