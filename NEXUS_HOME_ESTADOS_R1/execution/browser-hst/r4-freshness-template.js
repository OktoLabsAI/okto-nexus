async page=>{
 const cfg=__CONFIG__,checks=[],reads=[];
 const check=(id,ok,detail)=>{checks.push({id,ok,detail});if(!ok)throw Error(id);};
 try{
  const badge=page.locator('[data-home-badge="Idle"]').first();
  await badge.waitFor({timeout:15000});
  const r=await page.request.get(cfg.url+'/api/v1/home/harness-board?presentation_version=2&workspace_id='+cfg.workspace_id);
  const board=(await r.json()).data;
  check('optional-source-disabled-current-proof',board.source_status.external==='disabled'&&board.operational_summary.idle.value===1&&board.columns.active.items[0].operational_status.freshness==='current',board.source_status);
  check('current-partial-idle-not-last-known',(await badge.innerText()).trim()==='Idle',await badge.innerText());
  check('current-summary-not-previous',!(await page.getByRole('region',{name:'Project overview'}).innerText()).includes('Previous snapshot'),await page.getByRole('region',{name:'Project overview'}).innerText());
  await page.screenshot({path:cfg.freshScreenshot,fullPage:true});
  page.on('response',async response=>{if(new URL(response.url()).pathname==='/api/v1/home/harness-board'&&response.status()===200){const b=(await response.json()).data;reads.push({at:Date.now(),revision:b.revision});}});
  await page.getByRole('button',{name:'Pause display',exact:true}).click();
  await page.waitForTimeout(32000);
  check('paused-two-successful-identical-polls',reads.length>=2&&new Set(reads.map(x=>x.revision)).size===1,reads.slice());
  check('paused-current-still-fresh',(await badge.innerText()).trim()==='Idle',await badge.innerText());
  check('paused-no-false-update',!(await page.locator('body').innerText()).includes('Updates are available'),true);
  // A deliberate transport failure, not a forged canonical DTO or ACL result.
  await page.route('**/api/v1/home/harness-board?*',route=>route.abort('failed'),{times:1});
  await page.getByRole('button',{name:'Refresh',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('[data-home-badge="Idle"]')?.textContent?.includes('Last known:'));
  check('failed-read-stale-not-fresh',(await badge.innerText()).includes('Last known:'),await badge.innerText());
  check('failed-read-alert',await page.getByRole('alert').count()>0,await page.getByRole('alert').allTextContents());
  await page.screenshot({path:cfg.failedScreenshot,fullPage:false});
  await page.getByRole('button',{name:'Refresh',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('[data-home-badge="Idle"]')?.textContent?.trim()==='Idle');
  check('successful-read-recovers-current-while-paused',(await badge.innerText()).trim()==='Idle',await badge.innerText());
  return {status:'PASS_SUBSET',checks,reads,limits:['One controlled browser transport abort; not real server or authority failure','No Working qualification on R4','Functional host load may include installed tests']};
 }catch(error){return {status:'FAIL',error:String(error),checks,reads,body:await page.locator('body').innerText()};}
}
