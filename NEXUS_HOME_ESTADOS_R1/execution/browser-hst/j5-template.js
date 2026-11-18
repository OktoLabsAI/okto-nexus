async page=>{
 const cfg=__CONFIG__,checks=[];
 const check=(id,ok,detail)=>{checks.push({id,ok,detail});if(!ok)throw Error(id);};
 try{
  const response=await page.request.get(cfg.url+'/api/v1/home/harness-board?presentation_version=2&workspace_id='+cfg.workspace_id);
  const board=(await response.json()).data;
  const rows=board.columns.results.items.filter(x=>x.kind==='delivery');
  const candidates=rows.filter(x=>x.result?.detail_target?.operation_id===cfg.operation_id||x.result?.source_ref?.id===cfg.operation_id||x.entry?.target?.operation_id===cfg.operation_id);
  const expected=cfg.stage==='verifying'?'verifying':cfg.stage==='completed'?'completed':'claimed';
  const row=candidates.find(x=>x.delivery_semantics?.task_state===expected);
  check('exact-managed-turn-'+cfg.stage,!!row,{operation_id:cfg.operation_id,candidates:candidates.map(x=>({id:x.id,semantics:x.delivery_semantics}))});
  const meaning=row.delivery_semantics;
  check('canonical-outcome-not-inferred',meaning.evidence==='canonical'&&meaning.execution_outcome==='succeeded',meaning);
  if(cfg.stage==='claimed')check('turn-not-task-completion',meaning.scope==='turn'&&meaning.verification!=='approved'&&meaning.verification_evidence_ref===null,meaning);
  if(cfg.stage==='verifying')check('verification-pending-not-approved',meaning.verification==='pending'&&meaning.verification_evidence_ref===null,meaning);
  if(cfg.stage==='completed')check('positive-verification-evidence',meaning.verification==='approved'&&meaning.verification_evidence_ref!==null,meaning);
  await page.getByRole('button',{name:'Refresh',exact:true}).click();
  const column=page.locator('[data-home-column="results"]');
  const text=cfg.stage==='claimed'?'Task not yet completed':cfg.stage==='verifying'?'Awaiting verification':'Delivery verified';
  await column.getByText(text,{exact:true}).first().waitFor({timeout:15000});
  check('rendered-'+cfg.stage,true,await column.innerText());
  check('one-home-region',await page.getByTestId('home-board').count()===1,1);
  await column.scrollIntoViewIfNeeded();
  await page.screenshot({path:cfg.screenshot,fullPage:false});
  return {status:'PASS_SUBSET',stage:cfg.stage,checks,delivery_id:row.id,semantics:meaning};
 }catch(error){return {status:'FAIL',error:String(error),checks,body:await page.locator('body').innerText()};}
}
