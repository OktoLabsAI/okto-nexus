async page=>{
 const cfg=__CONFIG__,checks=[];if(cfg.window!=='POST_PERF_BROWSER_WINDOW_OPEN')throw Error('Window required');
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
