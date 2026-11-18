async page=>{
 const cfg=__CONFIG__,checks=[],posts=[];if(cfg.window!=='REMAINING_FUNCTIONAL_WINDOW_OPEN')throw Error('Root review/window required');
 const check=(id,ok,detail)=>{checks.push({id,ok,detail});if(!ok)throw Error(id);};page.on('request',r=>{if(r.method()!=='GET')posts.push({method:r.method(),path:new URL(r.url()).pathname});});
 try{
  check('fresh-original-question-window',Date.parse(cfg.a.expires_at)-Date.now()>60000&&Date.parse(cfg.b.expires_at)-Date.now()>60000,true);
  await page.getByRole('button',{name:'Refresh',exact:true}).click();const respond=page.locator('[data-home-column="needs_you"]').getByRole('button',{name:'Respond',exact:true});await respond.waitFor({timeout:10000});await respond.click();
  const dialog=page.getByRole('dialog',{name:'Activity detail'}),answer=dialog.getByLabel('Choose fixture output format',{exact:true});await answer.waitFor({timeout:10000});
  check('a-canonical-session-on-form',(await dialog.innerText()).includes(cfg.a.approval_key.session_id),cfg.a.approval_key.session_id);
  await answer.selectOption(['0']);await answer.focus();await answer.evaluate(e=>{window.__remainingDraft=e;});
  await page.keyboard.press('Escape');await dialog.getByText('Discard unsaved changes?',{exact:true}).waitFor();await dialog.getByRole('button',{name:'Keep editing',exact:true}).click();
  check('escape-cancel-keeps-exact-draft',await answer.evaluate(e=>e===window.__remainingDraft&&e.selectedOptions.length===1&&e.selectedOptions[0].value==='0'),true);
  const project=page.locator('select[aria-label="Project"]');
  check('modal-prevents-project-switch-bypass',await project.evaluate(e=>!!e.closest('[inert]')||Array.from(document.querySelectorAll('dialog:modal')).some(d=>!d.contains(e))),true);
  await answer.focus();
  await page.keyboard.press('Escape');await dialog.getByRole('button',{name:'Discard changes',exact:true}).click();await dialog.waitFor({state:'hidden'});await project.selectOption(cfg.b.approval_key.workspace_id);
  await respond.waitFor({timeout:10000});await respond.click();await answer.waitFor({timeout:10000});
  check('b-new-occurrence-no-copied-answer',cfg.a.request_id!==cfg.b.request_id&&(await dialog.innerText()).includes(cfg.b.approval_key.session_id)&&!(await dialog.innerText()).includes(cfg.a.approval_key.session_id)&&await answer.evaluate(e=>e!==window.__remainingDraft&&e.selectedOptions.length===0),true);
  await answer.selectOption(['0']);await answer.focus();
  check('no-ui-post-before-auth-revocation',posts.length===0,posts);
  return {status:'READY_REAL_LOGOUT',checks,posts,limits:['Actual modal prevents switching directly while open. Project change follows explicit Escape discard; no forced DOM onchange.','Fresh separate B occurrence; no decision/TTL renewal']};
 }catch(error){return {status:'FAIL_OR_INCOMPLETE',error:String(error),checks,posts};}
}
