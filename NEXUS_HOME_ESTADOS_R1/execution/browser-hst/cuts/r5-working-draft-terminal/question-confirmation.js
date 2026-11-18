async page=>{
 const cfg={"url": "http://127.0.0.1:58457", "workspace_id": "wsr_bdc2ab06f2e64c49dd8c3d38f03ef3e9", "card_id": "home_group_2779834cf2ca2df40785f94c261a84ac7c20ccf120c020ae3269add0618c5ddd", "request_id": "r4request_6a0a56c8536ba7b7f42f7f9d1c1b64719250279c0738f809cde4c1a1849c00f8", "stage": "confirmation", "activity": "awaiting_confirmation", "apiOnly": true},checks=[];
 const check=(id,ok,detail)=>{checks.push({id,ok,detail});if(!ok)throw Error(id);};
 try{
  let board;
  for(let i=0;i<40;i++){
   const r=await page.request.get(cfg.url+'/api/v1/home/harness-board?presentation_version=2&workspace_id='+cfg.workspace_id);
   board=(await r.json()).data;
   const cards=Object.values(board.columns).flatMap(c=>c.items).filter(x=>x.kind==='harness');
   if(cards.some(c=>c.operational_status?.activity===cfg.activity))break;
   await page.waitForTimeout(100);
  }
  const col=cfg.stage==='parallel'?'active':'needs_you';
  const card=board.columns[col].items.find(x=>x.kind==='harness'&&x.id===cfg.card_id);
  check('canonical-'+cfg.stage,card?.operational_status?.activity===cfg.activity,card?.operational_status);
  if(cfg.stage==='parallel'){
   check('independent-exact-request',board.columns.needs_you.items.some(x=>x.kind==='request'&&x.request.source_id===cfg.request_id),board.columns.needs_you.items.map(x=>x.id));
   check('not-globally-blocked',card.blocks_harness===false,card.blocks_harness);
  }
  if(cfg.stage==='blocked'){
   check('same-request-incorporated',card.requests_preview.some(x=>x.request.source_id===cfg.request_id),card.blocking_request_ids);
   check('single-card-full-block',card.blocks_harness===true&&!board.columns.active.items.some(x=>x.id===cfg.card_id),true);
   check('parallel-result-retained',board.columns.results.items.some(x=>x.kind==='delivery'),board.columns.results.items.length);
  }
  if(cfg.stage==='confirmation')check('recorded-not-resumed',card.placement_reason==='awaiting_native_confirmation'&&card.operational_status.awaiting_native_confirmation&&card.resume_confirmation_refs.some(x=>x.request_id===cfg.request_id),card.resume_confirmation_refs);
  if(cfg.apiOnly){
   const dialog=page.getByRole('dialog',{name:'Activity detail'});
   check('same-panel-remains-open',await dialog.count()===1,1);
   check('panel-recorded-not-applied',(await dialog.innerText()).includes('does not prove application'),true);
   return {status:'PASS_SUBSET',stage:cfg.stage,checks,board,limits:['Board confirmation is API proof while existing modal remains open; no underlay interaction']};
  }
  const refresh=page.getByRole('button',{name:'Refresh',exact:true});
  if(await page.getByRole('dialog').count()===0)await refresh.click();
  const expected=cfg.stage==='parallel'?'Working':cfg.stage==='blocked'?'Waiting for your response':'Waiting for resume confirmation';
  await page.locator('[data-home-harness="'+cfg.card_id+'"]').getByText(new RegExp(expected)).first().waitFor({timeout:10000});
  check('rendered-'+cfg.stage,true,await page.locator('[data-home-harness="'+cfg.card_id+'"]').innerText());
  return {status:'PASS_SUBSET',stage:cfg.stage,checks,board};
 }catch(error){return {status:'FAIL',error:String(error),checks,body:await page.locator('body').innerText()};}
}
