async page=>{
 const cfg=__CONFIG__,checks=[],posts=[],polls=[];
 const check=(id,ok,detail)=>{checks.push({id,ok,detail});if(!ok)throw Error(id);};
 try{
  page.on('response',async r=>{if(r.request().method()==='POST')posts.push({path:new URL(r.url()).pathname,status:r.status(),body:await r.json()});});
  page.on('response',async r=>{if(new URL(r.url()).pathname==='/api/v1/home/harness-board'&&r.status()===200){const b=(await r.json()).data;polls.push({at:Date.now(),revision:b.revision});}});
  if(cfg.pollWhileDirty)await page.getByRole('button',{name:'Pause display',exact:true}).click();
  await page.locator('[data-home-column="needs_you"]').getByRole('button',{name:'Respond',exact:true}).click();
  const dialog=page.getByRole('dialog',{name:'Activity detail'});
  const answer=dialog.getByLabel('Choose fixture output format',{exact:true});
  await answer.waitFor({timeout:10000});
  check('single-exact-question-form',await page.getByRole('dialog').count()===1&&await answer.count()===1,1);
  await answer.selectOption(['0']);
  if(cfg.pollWhileDirty){
   await answer.focus();const start=polls.length;
   await page.waitForTimeout(32000);
   const observed=polls.slice(start);
   check('dirty-two-real-identical-polls',observed.length>=2&&new Set(observed.map(x=>x.revision)).size===1,observed);
   check('dirty-focus-and-value-retained',await answer.evaluate(e=>document.activeElement===e&&e.selectedOptions.length===1&&e.selectedOptions[0].value==='0'),true);
   check('dirty-identical-no-update-notice',!(await page.locator('body').innerText()).includes('Updates are available'),true);
  }
  await dialog.getByRole('button',{name:'Close modal',exact:true}).click();
  await dialog.getByText('Discard unsaved changes?',{exact:true}).waitFor();
  check('dirty-close-guard',true,'Discard unsaved changes?');
  await dialog.getByRole('button',{name:'Keep editing',exact:true}).click();
  check('draft-preserved',JSON.stringify(await answer.evaluate(e=>Array.from(e.selectedOptions,o=>o.value)))==='["0"]',true);
  check('zero-post-before-explicit-answer',posts.length===0,posts.slice());
  await dialog.getByRole('button',{name:'Send answer',exact:true}).click();
  await dialog.getByTestId('canonical-native-status').waitFor({timeout:15000});
  const status=await dialog.getByTestId('canonical-native-status').innerText();
  check('recorded-not-provider-applied',status.includes('does not prove application'),status);
  check('one-canonical-decision',posts.length===1&&posts[0].path==='/api/v1/runtime-management/runtime/approval-decisions'&&[200,202].includes(posts[0].status),posts);
  if(!cfg.keepOpen){await dialog.getByRole('button',{name:'Close modal',exact:true}).click();await dialog.waitFor({state:'hidden'});}
  return {status:'PASS_SUBSET',checks,posts,polls,kept_open:!!cfg.keepOpen,snapshot:await dialog.count()?await dialog.ariaSnapshot():null};
 }catch(error){return {status:'FAIL',error:String(error),checks,posts,polls,body:await page.locator('body').innerText()};}
}
