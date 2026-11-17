async page=>{
 const cfg={"url": "http://127.0.0.1:60048", "workspace_id": "wsr_1d768338242d64e2d2a5c2de51f26ce6", "screenshot": "D:\\Projetos\\Techridy\\okto_labs_okto_nexus\\output\\playwright\\home-states\\r6-final-mobile.png"},checks=[],posts=[];const check=(id,ok,detail)=>{checks.push({id,ok,detail});if(!ok)throw Error(id);};
 page.on('request',r=>{if(r.method()!=='GET')posts.push({method:r.method(),path:new URL(r.url()).pathname});});
 try{
  let board;for(let i=0;i<60;i++){const r=await page.request.get(cfg.url+'/api/v1/home/harness-board?presentation_version=2&workspace_id='+cfg.workspace_id);board=(await r.json()).data;if(board.columns.active.items.some(x=>x.operational_status?.activity==='working'))break;await page.waitForTimeout(100);}
  const card=board.columns.active.items.find(x=>x.kind==='harness'&&x.operational_status?.activity==='working');
  check('canonical-working-current',card?.operational_status.freshness==='current',card?.operational_status);
  check('independent-question-retained',board.columns.needs_you.items.some(x=>x.kind==='request'),board.columns.needs_you.items.map(x=>x.id));
  check('parallel-not-blocked',card?.blocks_harness===false,card?.blocks_harness);
  await page.getByRole('button',{name:'Refresh',exact:true}).click();
  await page.locator('[data-home-harness="'+card.id+'"]').getByText('Working',{exact:true}).waitFor({timeout:10000});
  check('working-rendered-current',!(await page.locator('[data-home-harness="'+card.id+'"]').innerText()).includes('Last known'),true);
  await page.getByRole('button',{name:'Ask for work or chat',exact:true}).focus();await page.keyboard.press('Enter');
  const dialog=page.getByRole('dialog',{name:'New request'});await dialog.waitFor();
  check('keyboard-opens-single-context',await page.getByRole('dialog').count()===1,true);
  await dialog.getByTestId('meta-kind-message').click();
  check('chat-intent-label',await dialog.getByRole('button',{name:'Chat',exact:true}).count()===1&&await dialog.getByRole('button',{name:'Send chat message',exact:true}).count()===1,true);
  await dialog.getByTestId('meta-kind-handoff').click();
  check('work-intent-label',await dialog.getByRole('button',{name:'Ask for work',exact:true}).count()>=1&&await dialog.getByRole('combobox',{name:'Project for this interaction',exact:true}).count()===1,true);
  await page.keyboard.press('Escape');
  // Kind selection may mark the canonical composer dirty; preserve its real guard.
  const discard=page.getByRole('button',{name:'Discard changes',exact:true});if(await discard.count())await discard.click();
  await dialog.waitFor({state:'hidden'});
  check('keyboard-close-returns-focus',await page.getByRole('button',{name:'Ask for work or chat',exact:true}).evaluate(e=>document.activeElement===e),true);
  await page.setViewportSize({width:360,height:800});
  check('mobile-three-columns-no-overflow',await page.locator('[data-home-column]').count()===3&&await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  await page.screenshot({path:cfg.screenshot});
  check('zero-write-intent-inspection',posts.length===0,posts);
  return {status:'PASS_SUBSET',checks,posts,limits:['Actual canonical Working and independent native question; Chat/Ask labels and canonical test IDs inspected only, no send/payload integration claim','One inert Codex protocol fixture, not three native families; keyboard subset, not full accessibility or AT']};
 }catch(error){return {status:'FAIL',error:String(error),checks,posts,body:await page.locator('body').innerText()};}
}
