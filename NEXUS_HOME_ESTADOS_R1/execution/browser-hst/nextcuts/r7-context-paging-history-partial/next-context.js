async page=>{
 const cfg={"window": "POST_PERF_BROWSER_WINDOW_OPEN", "url": "http://127.0.0.1:53687", "workspace_id": "wsr_5bfdda66177c96524163e86eba9b4f21", "request_id": "r4request_1d8a0aa8a91f262facb5adc7522e653f4b561f153688cf19f89b1a0a4989928a", "session_id": "ses_473151227dc421ea064ebf9f713519ea", "question_expires_at": "2026-11-17T20:36:28.927000+00:00", "storage": "C:\\Users\\jpamb\\AppData\\Local\\Temp\\nexus-hst-browser-i1wx2xv_\\control\\browser-storage.private.json", "reference": {"server_id": "srv_7e9944e285d6c058d1a76fade202fd2c", "executor_id": "exe_1a0f64917ff5f8a2d9faa214208e6273", "binding_id": "bind_12888ad33dbc707b3ef02b592d6489dc", "endpoint_id": "ep_339f0516d0396897163143064ca818c7", "agent_id": "hst-a", "workspace_id": "wsr_5bfdda66177c96524163e86eba9b4f21", "workspace_binding_id": "wxb_fc509392bfaf533e570ef7e614c69ed7"}, "workspace_b": "wsr_5df679001b3401e70d3adf2a056c9bc1", "card_id": "home_group_4c8ac5147967db10da87c9ef273b5f58af175956cf9d050814d82f09b29a1fd6"},checks=[];if(cfg.window!=='POST_PERF_BROWSER_WINDOW_OPEN')throw Error('Window required');
 const check=(id,ok,detail)=>{checks.push({id,ok,detail});if(!ok)throw Error(id);};
 try{
  await page.addInitScript(({workspace})=>{localStorage.setItem('okto-nexus-home-operational','enabled');localStorage.setItem('okto-nexus-workspace',workspace);localStorage.setItem('okto-nexus:metrics-opt-in-prompt-dismissed:1.0.0',new Date().toISOString());},{workspace:cfg.workspace_id});
  await page.goto(cfg.url,{waitUntil:'domcontentloaded'});
  const card=page.locator('[data-home-harness="'+cfg.card_id+'"]');await card.waitFor({timeout:10000});
  await card.getByRole('button',{name:'Follow activity',exact:true}).click();
  const dialog=page.getByRole('dialog',{name:'Activity detail'}),selector=dialog.getByRole('combobox',{name:'Choose a session',exact:true});
  await selector.waitFor({timeout:10000});
  await page.waitForFunction(()=>{const e=document.querySelector('dialog select');const b=Array.from(document.querySelectorAll('dialog button')).find(e=>e.textContent==='Load more sessions');return e&&e.options.length>=11&&b&&!b.disabled;});
  let options=[],selected=null;
  // Twelve actual sessions exist for this binding; at most two10-item pages.
  // Never replace the known target by the first/newest option.
  for(let pageIndex=0;pageIndex<2;pageIndex++){
   options=await selector.locator('option').evaluateAll(es=>es.map(e=>({value:e.value,text:e.textContent})).filter(e=>e.value));
   selected=options.find(o=>JSON.parse(o.value).includes(cfg.session_id));if(selected)break;
   const next=dialog.getByRole('button',{name:'Load more sessions',exact:true});
   if(!await next.count())break;const before=options.length;await next.click();
   await page.waitForFunction(({before})=>{const e=document.querySelector('dialog select');return e&&e.options.length-1>before;},{before});
  }
  check('canonical-known-session-found-by-bounded-paging',!!selected,{session_id:cfg.session_id,loaded_options:options.length});
  await selector.selectOption(selected.value);
  // Restore a real first-page cursor while preserving the explicit selection.
  await dialog.getByRole('button',{name:'Refresh sessions',exact:true}).click();
  await page.waitForFunction(()=>{const b=Array.from(document.querySelectorAll('dialog button')).find(e=>e.textContent==='Load more sessions');return b&&!b.disabled;});
  const more=dialog.getByRole('button',{name:'Load more sessions',exact:true});await more.waitFor({timeout:10000});await more.waitFor({state:'visible'});
  check('real-relation-has-next-page',await more.isEnabled(),options.length);
  await dialog.evaluate(e=>{window.__nextPanel=e;});
  return {status:'READY_CANONICAL_ARRIVAL',checks,selected:selected.value,relation_path:'/api/v1/home/harness-board/cards/'+encodeURIComponent(cfg.card_id)+'/sessions',initial_ids:options.map(x=>JSON.parse(x.value).at(-1))};
 }catch(error){return {status:'FAIL_OR_INCOMPLETE',error:String(error),checks};}
}
