async page=>{
 const cfg={"window": "POST_PERF_BROWSER_WINDOW_OPEN", "url": "http://127.0.0.1:58133", "workspace_id": "wsr_1fe1602d67b5ed178d5284e2ebc9493e", "request_id": "r4request_2dada63c4e7cb1e091daf6cd2bf00af3c51872ba1d40294a00c8c5742b80aac4", "session_id": "ses_4466b29a6a854605aa7391f0db5ac126", "question_expires_at": "2026-11-17T20:25:42.247000+00:00", "storage": "C:\\Users\\jpamb\\AppData\\Local\\Temp\\nexus-hst-browser-sy8tw3k0\\control\\browser-storage.private.json", "reference": {"server_id": "srv_0d6a09e6bbca331a1de65cba71e5876f", "executor_id": "exe_f8aa87f7bd372f9fa2262bc8a2f8642d", "binding_id": "bind_86addfffa26a94698861876d7e9a7741", "endpoint_id": "ep_ceab3f72c0bb8cc38c9790ee33e934a5", "agent_id": "hst-a", "workspace_id": "wsr_1fe1602d67b5ed178d5284e2ebc9493e", "workspace_binding_id": "wxb_9880639ebaa9f290478cfcde6a9bba7a"}, "workspace_b": "wsr_161c454ae35e001b412a093518575600", "card_id": "home_group_76d8bb69f06de0238878e6b9096babfec62b3f68097dad4d02a216ccb3ff3bb5"},checks=[];if(cfg.window!=='POST_PERF_BROWSER_WINDOW_OPEN')throw Error('Window required');
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
