async page=>{
 const cfg={"url": "http://127.0.0.1:53720", "workspace_id": "wsr_d6ab987ce5a5ca58abb6386580ec8b8b", "negative": [{"operation_id": "op_12fff6eea336fdb5f3b5605c2734e9c9", "session_id": "ses_745c58796e9adbdbf3c846623245304b", "outcome": "failed"}, {"operation_id": "op_497a2d723aea659103f900077bd7d725", "session_id": "ses_42050b2a925aae9475b6ecd3d2960586", "outcome": "cancelled"}], "screenshot": "D:\\Projetos\\Techridy\\okto_labs_okto_nexus\\output\\playwright\\home-states\\r5-negative.png"},checks=[];
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
