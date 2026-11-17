async page=>{
 const cfg=__CONFIG__,checks=[],posts=[],snapshots=[];const check=(id,ok,detail)=>{checks.push({id,ok,detail});if(!ok)throw Error(id);};
 page.on('request',r=>{if(r.method()!=='GET')posts.push({method:r.method(),path:new URL(r.url()).pathname});});
 try{
  await page.getByRole('button',{name:'Ask for work or chat',exact:true}).waitFor({timeout:10000});
  snapshots.push(await page.locator('main').ariaSnapshot());
  await page.getByRole('button',{name:'Ask for work or chat',exact:true}).click();
  const dialog=page.getByRole('dialog',{name:'New request'});await dialog.waitFor();snapshots.push(await dialog.ariaSnapshot());
  const handoff=dialog.getByTestId('meta-kind-handoff'),message=dialog.getByTestId('meta-kind-message');
  await handoff.click();
  check('ask-pressed-and-canonical-id',await handoff.getAttribute('aria-pressed')==='true'&&await message.getAttribute('aria-pressed')==='false', {handoff:await handoff.getAttribute('aria-pressed'),message:await message.getAttribute('aria-pressed')});
  check('ask-submit-label',await dialog.getByRole('button',{name:'Ask for work',exact:true}).count()===2,true);
  await message.click();
  check('chat-pressed-and-canonical-id',await message.getAttribute('aria-pressed')==='true'&&await handoff.getAttribute('aria-pressed')==='false',{handoff:await handoff.getAttribute('aria-pressed'),message:await message.getAttribute('aria-pressed')});
  check('chat-submit-and-project-label',await dialog.getByRole('button',{name:'Send chat message',exact:true}).count()===1&&await dialog.getByRole('combobox',{name:'Project for this interaction',exact:true}).count()===1,true);
  await page.keyboard.press('Escape');const discard=page.getByRole('button',{name:'Discard changes',exact:true});if(await discard.count())await discard.click();await dialog.waitFor({state:'hidden'});
  await page.locator('[data-testid="home-follow-up"]').scrollIntoViewIfNeeded();await page.screenshot({path:cfg.desktop});
  await page.setViewportSize({width:360,height:800});
  snapshots.push(await page.locator('body').ariaSnapshot());
  const close=page.getByRole('button',{name:'Close navigation',exact:true});if(await close.count())await close.click();
  await page.waitForTimeout(250);snapshots.push(await page.locator('main').ariaSnapshot());
  check('mobile-navigation-closed',await close.count()===0,true);
  const columns=page.locator('[data-home-column]');check('three-columns-no-horizontal-overflow',await columns.count()===3&&await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  const geometry=[];
  for(const name of ['active','needs_you','results']){
   const col=page.locator('[data-home-column="'+name+'"]');await col.scrollIntoViewIfNeeded();
   const box=await col.boundingBox();geometry.push({column:name,...box});
   check('visible-uncovered-'+name,await col.evaluate(e=>{const r=e.getBoundingClientRect(),x=Math.min(innerWidth-5,Math.max(5,r.x+r.width/2)),y=Math.min(innerHeight-5,Math.max(5,r.y+20));return e.contains(document.elementFromPoint(x,y));}),box);
   await page.screenshot({path:cfg.mobile.replace('.png','-'+name+'.png')});
  }
  check('stacked-mobile-columns',geometry[0].y<geometry[1].y&&geometry[1].y<geometry[2].y,geometry);
  check('zero-post-before-after-choice',posts.length===0,posts);
  return {status:'PASS_SUBSET',checks,posts,snapshots,limits:['Baseline retained Idle sessions; no pending native question','Choice states and canonical test IDs inspected, no composer send/payload or provider claim','Previous mobile screenshot had navigation overlay; this derivative closes it explicitly, not a product defect']};
 }catch(error){return {status:'FAIL',error:String(error),checks,posts,snapshots,body:await page.locator('body').innerText()};}
}
