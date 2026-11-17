async page=>{const cfg=__CONFIG__,checks=[],posts=[];if(cfg.window!=='POST_PERF_BROWSER_WINDOW_OPEN')throw Error('Window required');const check=(id,ok,detail)=>{checks.push({id,ok,detail});if(!ok)throw Error(id);};page.on('request',r=>{if(r.method()!=='GET')posts.push({method:r.method(),path:new URL(r.url()).pathname});});try{const dialog=page.getByRole('dialog',{name:'Activity detail'});await dialog.getByRole('button',{name:'Close modal',exact:true}).click();await dialog.waitFor({state:'hidden'});
  check('original-question-still-within-expiry',Date.parse(cfg.question_expires_at)-Date.now()>15000,{expires_at:cfg.question_expires_at});
  await page.locator('[data-home-column="needs_you"]').getByRole('button',{name:'Respond',exact:true}).click();
  const answer=dialog.getByLabel('Choose fixture output format',{exact:true});await answer.waitFor({timeout:10000});await answer.selectOption(['0']);await answer.focus();await answer.evaluate(e=>{window.__nextDraft=e;});
  await page.keyboard.press('Escape');await dialog.getByText('Discard unsaved changes?',{exact:true}).waitFor();await dialog.getByRole('button',{name:'Keep editing',exact:true}).click();
  check('escape-cancel-retains-same-draft-and-request',await answer.evaluate(e=>e===window.__nextDraft&&e.selectedOptions.length===1&&e.selectedOptions[0].value==='0')&&(await dialog.innerText()).includes(cfg.session_id),true);
  const project=page.locator('select[aria-label="Project"]');
  const inert=await project.evaluate(e=>!!e.closest('[inert]')||Array.from(document.querySelectorAll('dialog[open]')).some(d=>!d.contains(e)));
  check('project-switch-not-forced-through-modal',inert,true);
  await page.keyboard.press('Escape');await dialog.getByRole('button',{name:'Discard changes',exact:true}).click();await dialog.waitFor({state:'hidden'});
  await project.selectOption(cfg.workspace_b);
  await page.waitForTimeout(600);
  await page.locator('[data-home-column="needs_you"]').getByRole('button',{name:'Respond',exact:true}).click();await answer.waitFor({timeout:10000});
  check('no-draft-copied-to-project-b',await answer.evaluate(e=>e!==window.__nextDraft&&Array.from(e.selectedOptions).every(o=>o.value===''))&&!(await dialog.innerText()).includes(cfg.session_id),true);
check('zero-ui-posts',posts.length===0,posts);return {status:'PASS_BROWSER_SUBSET',checks,posts,limits:['Project selector is inert while modal is open; actual switch follows explicit Escape discard','No native decision or provider']};}catch(error){return {status:'FAIL_OR_INCOMPLETE',error:String(error),checks,posts};}}
