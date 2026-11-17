async page=>{
 const cfg={"window": "REMAINING_FUNCTIONAL_WINDOW_OPEN", "url": "http://127.0.0.1:49961", "workspace_id": "wsr_224ac397cb6e67caa17c8c657ea2f6a7", "a": {"request_id": "r4request_c57d7ee60945deba1fefa85b73639654f35d52197484554281c7a4fcf451e82c", "approval_key": {"server_id": "srv_d4e98283718ad7b367155286e0261544", "executor_id": "exe_7ab16056751715f460c9abe404ceec39", "binding_id": "bind_d358ebe880a0fae3233d6413f36a89f6", "agent_id": "hst-a", "workspace_id": "wsr_224ac397cb6e67caa17c8c657ea2f6a7", "session_id": "ses_45484dae57343092638d834138e72c9f", "session_owner_generation": 1, "canonical_request_id": "r4request_c57d7ee60945deba1fefa85b73639654f35d52197484554281c7a4fcf451e82c", "kind": "native_input"}, "expires_at": "2026-11-17T20:53:27.209000+00:00"}, "b": {"request_id": "r4request_1cf67d820fa5aeb4d35db28dc39768146efb069cd0d381e001a54d139e2e884c", "approval_key": {"server_id": "srv_d4e98283718ad7b367155286e0261544", "executor_id": "exe_7ab16056751715f460c9abe404ceec39", "binding_id": "bind_21c72f9e20dd9dfdbd29196373b5f7d3", "agent_id": "hst-b", "workspace_id": "wsr_feb56794c3fd183296b79f36744b2a53", "session_id": "ses_6edba0b35b98c9d428ef5106515352b9", "session_owner_generation": 1, "canonical_request_id": "r4request_1cf67d820fa5aeb4d35db28dc39768146efb069cd0d381e001a54d139e2e884c", "kind": "native_input"}, "expires_at": "2026-11-17T20:53:28.019000+00:00"}},checks=[],posts=[];if(cfg.window!=='REMAINING_FUNCTIONAL_WINDOW_OPEN')throw Error('Root review/window required');
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
