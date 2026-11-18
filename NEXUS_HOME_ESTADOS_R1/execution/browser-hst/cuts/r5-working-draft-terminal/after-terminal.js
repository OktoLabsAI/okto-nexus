async page=>{
 const cfg={"url": "http://127.0.0.1:58457", "workspace_id": "wsr_bdc2ab06f2e64c49dd8c3d38f03ef3e9", "operation_id": "op_78424f48b208632745af8d8b550d7c81", "session_id": "ses_65613d37fd81cd60b15827b3913d6487", "text": "HST synthetic output ses_65613d37fd81cd60b15827b3913d6487", "other_text": "HST synthetic output ses_3f1695c4961e5746d9f7fa2be7a63a3a", "other_session_id": "ses_3f1695c4961e5746d9f7fa2be7a63a3a", "screenshot": "D:\\Projetos\\Techridy\\okto_labs_okto_nexus\\output\\playwright\\home-states\\r5-same-panel-output.png"},checks=[];
 const check=(id,ok,detail)=>{checks.push({id,ok,detail});if(!ok)throw Error(id);};
 try{
  let state;
  for(let i=0;i<60;i++){
   const r=await page.request.get(cfg.url+'/api/v1/runtime-management/runtime/operations/'+cfg.operation_id);
   state=await r.json();state=state.data??state;
   if(state.executor_stage==='SUCCEEDED')break;
   await page.waitForTimeout(100);
  }
  check('actual-post-answer-turn-terminal',state.executor_stage==='SUCCEEDED',state.executor_stage);
  const dialog=page.getByRole('dialog',{name:'Activity detail'});
  check('same-dialog-still-open',await dialog.count()===1,1);
  const latest=dialog.getByRole('button',{name:'Latest events',exact:true});
  if(await latest.count())await latest.click();
  await dialog.getByText(cfg.text,{exact:false}).first().waitFor({timeout:10000});
  check('same-panel-new-native-output',true,cfg.session_id);
  check('no-other-session-output',!(await dialog.innerText()).includes(cfg.other_text),cfg.other_session_id);
  const response=await page.request.get(cfg.url+'/api/v1/home/harness-board?presentation_version=2&workspace_id='+cfg.workspace_id);
  const board=(await response.json()).data;
  check('terminal-returns-idle-without-reply-inference',board.operational_summary.idle.value===1&&board.operational_summary.resume_confirmations.value===0,board.operational_summary);
  check('new-delivery-canonical-exact-operation',board.columns.results.items.some(x=>x.kind==='delivery'&&x.result?.detail_target?.operation_id===cfg.operation_id),board.columns.results.items.map(x=>x.id));
  await page.screenshot({path:cfg.screenshot,fullPage:false});
  return {status:'PASS_SUBSET',checks,body:await dialog.innerText(),board,limits:['Same panel live output and canonical delivery API; no claim that every related-preview row auto-refreshed']};
 }catch(error){return {status:'FAIL',error:String(error),checks,body:await page.locator('body').innerText()};}
}
