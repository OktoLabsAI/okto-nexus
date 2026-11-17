async page=>{
 const cfg={"window": "POST_PERF_BROWSER_WINDOW_OPEN", "url": "http://127.0.0.1:63337", "workspace_id": "wsr_e17bf1231fde75d2233075557304e468", "request_id": "r4request_cd923f9fb71ba93a39bd34496b5c9b11ed0919c8e3befc69afa645f726032654", "session_id": "ses_e0f9da495abe3f02b6178bdb42252465", "question_expires_at": "2026-11-17T20:31:21.757000+00:00", "storage": "C:\\Users\\jpamb\\AppData\\Local\\Temp\\nexus-hst-browser-lckx7fa_\\control\\browser-storage.private.json", "reference": {"server_id": "srv_380dd4a6b953890fc4385eb8f8fa40e0", "executor_id": "exe_d80244dc0c3d049f7268136e91554863", "binding_id": "bind_17e2fc6f0c194ad5da5b4bec76655ff9", "endpoint_id": "ep_b1299195465670c54711c28f40aed798", "agent_id": "hst-a", "workspace_id": "wsr_e17bf1231fde75d2233075557304e468", "workspace_binding_id": "wxb_19fa0f2514199169af9425b2077d343c"}, "workspace_b": "wsr_545f8aa3c22de57f864778128d9ec36a", "card_id": "home_group_09fc8217e9eeaaadd746340fabf4c661fae46f686e0b7a7438a0cefe5c4f433d"},checks=[];if(cfg.window!=='POST_PERF_BROWSER_WINDOW_OPEN')throw Error('Window required');
 const check=(id,ok,detail)=>{checks.push({id,ok,detail});if(!ok)throw Error(id);};
 try{
  await page.addInitScript(({workspace})=>{localStorage.setItem('okto-nexus-home-operational','enabled');localStorage.setItem('okto-nexus-workspace',workspace);localStorage.setItem('okto-nexus:metrics-opt-in-prompt-dismissed:1.0.0',new Date().toISOString());},{workspace:cfg.workspace_id});
  await page.goto(cfg.url,{waitUntil:'domcontentloaded'});
  const card=page.locator('[data-home-harness="'+cfg.card_id+'"]');await card.waitFor({timeout:10000});
  await card.getByRole('button',{name:'Follow activity',exact:true}).click();
  const dialog=page.getByRole('dialog',{name:'Activity detail'}),selector=dialog.getByRole('combobox',{name:'Choose a session',exact:true});
  await selector.waitFor({timeout:10000});
  await page.waitForFunction(()=>{const e=document.querySelector('dialog select');const b=Array.from(document.querySelectorAll('dialog button')).find(e=>e.textContent==='Load more sessions');return e&&e.options.length>=11&&b&&!b.disabled;});
  const options=await selector.locator('option').evaluateAll(es=>es.map(e=>({value:e.value,text:e.textContent})).filter(e=>e.value));
  const selected=options.find(o=>JSON.parse(o.value).includes(cfg.session_id));
  check('canonical-selected-session-in-first-page',!!selected,cfg.session_id);
  await selector.selectOption(selected.value);
  const more=dialog.getByRole('button',{name:'Load more sessions',exact:true});await more.waitFor({timeout:10000});await more.waitFor({state:'visible'});
  check('real-relation-has-next-page',await more.isEnabled(),options.length);
  await dialog.evaluate(e=>{window.__nextPanel=e;});
  return {status:'READY_CANONICAL_ARRIVAL',checks,selected:selected.value,relation_path:'/api/v1/home/harness-board/cards/'+encodeURIComponent(cfg.card_id)+'/sessions',initial_ids:options.map(x=>JSON.parse(x.value).at(-1))};
 }catch(error){return {status:'FAIL_OR_INCOMPLETE',error:String(error),checks};}
}
