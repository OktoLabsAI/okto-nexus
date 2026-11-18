async page=>{
 const cfg={"url": "http://127.0.0.1:62116", "workspace_id": "wsr_9e0d86d954aab82a5f10f198b7deb8ea"},checks=[];
 const check=(id,ok,detail)=>{checks.push({id,ok,detail});if(!ok)throw Error(id);};
 try{
  const response=await page.request.get(cfg.url+'/api/v1/home/harness-board?presentation_version=2&workspace_id='+cfg.workspace_id);
  const raw=await response.json(),board=raw.data;
  check('actual-results-source-failed',response.status()===200&&board.source_status.results==='unavailable',board.source_status);
  check('other-sources-retained',board.source_status.connections==='ready'&&Object.values(board.columns).flatMap(c=>c.items).some(x=>x.kind==='harness'),board.operational_summary);
  check('results-unknown-never-zero',board.columns.results.total===null&&!board.columns.results.total_is_exact,board.columns.results.total);
  await page.getByRole('button',{name:'Refresh',exact:true}).click();
  await page.waitForTimeout(1000);
  check('partial-notice-rendered',(await page.locator('body').innerText()).includes('Some information is incomplete'),true);
  return {status:'PASS_SUBSET',checks,http:{status:response.status(),source_status:board.source_status},body:await page.locator('body').innerText()};
 }catch(error){return {status:'FAIL',error:String(error),checks,body:await page.locator('body').innerText()};}
}
