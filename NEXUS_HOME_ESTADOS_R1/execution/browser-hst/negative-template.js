async page=>{
 const cfg=__CONFIG__,checks=[];
 const check=(id,ok,detail)=>{checks.push({id,ok,detail});if(!ok)throw Error(id);};
 try{
  const response=await page.request.get(cfg.url+'/api/v1/home/harness-board?presentation_version=2&workspace_id='+cfg.workspace_id);
  const board=(await response.json()).data,items=board.columns.results.items;
  for(const expected of cfg.negative){
   const row=items.find(x=>x.kind==='delivery'&&x.result?.detail_target?.operation_id===expected.operation_id);
   check('canonical-'+expected.outcome,!!row&&row.delivery_semantics.execution_outcome===expected.outcome&&row.delivery_semantics.evidence==='canonical',row?.delivery_semantics);
   check('not-completed-or-verified-'+expected.outcome,row.delivery_semantics.task_state!=='completed'&&row.delivery_semantics.verification!=='approved',row.delivery_semantics);
  }
  check('harness-not-in-results',items.every(x=>x.kind!=='harness'),items.map(x=>x.kind));
  await page.getByRole('button',{name:'Refresh',exact:true}).click();
  for(const title of ['Execution ended with failure','Execution cancelled'])await page.locator('[data-home-column="results"]').getByText(title,{exact:true}).first().waitFor({timeout:10000});
  check('failed-cancelled-labels',true,await page.locator('[data-home-column="results"]').innerText());
  check('no-generic-retry-action',await page.getByRole('button',{name:'Retry',exact:true}).count()===0,true);
  await page.screenshot({path:cfg.screenshot,fullPage:false});
  return {status:'PASS_SUBSET',checks,board,limits:['No success+cleanup-pending producer fixture; that branch remains NOT_RUN here']};
 }catch(error){return {status:'FAIL',error:String(error),checks,body:await page.locator('body').innerText()};}
}
