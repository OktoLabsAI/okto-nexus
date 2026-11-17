async page=>{
 const cfg={"window": "POST_PERF_BROWSER_WINDOW_OPEN", "url": "http://127.0.0.1:53687", "workspace_id": "wsr_5bfdda66177c96524163e86eba9b4f21", "request_id": "r4request_1d8a0aa8a91f262facb5adc7522e653f4b561f153688cf19f89b1a0a4989928a", "session_id": "ses_473151227dc421ea064ebf9f713519ea", "question_expires_at": "2026-11-17T20:36:28.927000+00:00", "storage": "C:\\Users\\jpamb\\AppData\\Local\\Temp\\nexus-hst-browser-i1wx2xv_\\control\\browser-storage.private.json", "selected": "[\"srv_7e9944e285d6c058d1a76fade202fd2c\",\"exe_1a0f64917ff5f8a2d9faa214208e6273\",\"wsr_5bfdda66177c96524163e86eba9b4f21\",\"ses_473151227dc421ea064ebf9f713519ea\"]", "relation_path": "/api/v1/home/harness-board/cards/home_group_4c8ac5147967db10da87c9ef273b5f58af175956cf9d050814d82f09b29a1fd6/sessions", "workspace_b": "wsr_5df679001b3401e70d3adf2a056c9bc1"},checks=[],reads=[],posts=[],beforeUnload=[];if(cfg.window!=='POST_PERF_BROWSER_WINDOW_OPEN')throw Error('Window required');
 const check=(id,ok,detail)=>{checks.push({id,ok,detail});if(!ok)throw Error(id);};
 page.on('request',r=>{if(r.method()!=='GET')posts.push({method:r.method(),path:new URL(r.url()).pathname});});
 page.on('response',async r=>{if(new URL(r.url()).pathname===cfg.relation_path){const item={status:r.status(),at:Date.now()};if(r.status()===200){const raw=await r.json(),body=raw.data??raw;item.ids=body.items.map(x=>x.session_id);item.revision=body.revision;}reads.push(item);}});
 try{
  const dialog=page.getByRole('dialog',{name:'Activity detail'}),selector=dialog.getByRole('combobox',{name:'Choose a session',exact:true});
  await dialog.getByRole('button',{name:'Load more sessions',exact:true}).click();
  for(let i=0;i<120&&!reads.some(x=>x.status===200&&x.at>=(reads.find(y=>y.status===409)?.at??Infinity));i++)await page.waitForTimeout(100);
  const current=reads.find(x=>x.status===200&&x.at>=(reads.find(y=>y.status===409)?.at??Infinity));
  check('real409-followed-by-current-reread',!!current&&reads.some(x=>x.status===409),reads);
  check('same-panel-and-exact-selection',await dialog.evaluate(e=>e===window.__nextPanel)&&await selector.inputValue()===cfg.selected,true);
  const allowed=new Set([...current.ids,JSON.parse(cfg.selected).at(-1)]);
  await page.waitForFunction(expected=>{const e=document.querySelector('dialog select');if(!e)return false;const ids=Array.from(e.options).filter(o=>o.value).map(o=>JSON.parse(o.value).at(-1));return ids.length===expected.length&&ids.every(id=>expected.includes(id));},[...allowed]);
  const ids=await selector.locator('option').evaluateAll(es=>es.filter(e=>e.value).map(e=>JSON.parse(e.value).at(-1)));
  check('no-mixed-revision-or-duplicate-options',new Set(ids).size===ids.length&&ids.length===allowed.size&&ids.every(id=>allowed.has(id)),{ids,current_ids:current.ids});
  await dialog.getByRole('button',{name:'Close modal',exact:true}).click();await dialog.waitFor({state:'hidden'});
  const [server_id,executor_id,workspace_id,session_id]=JSON.parse(cfg.selected),target={kind:'session',server_id,executor_id,workspace_id,session_id};
  const url=new URL(cfg.url);url.searchParams.set('home_target',JSON.stringify(target));
  await page.goto(url.toString(),{waitUntil:'domcontentloaded'});await dialog.waitFor({timeout:10000});
  return {status:'PASS_F05_HISTORY_READY',checks,reads,posts,historyTarget:target};
 }catch(error){return {status:'FAIL_OR_INCOMPLETE',error:String(error),checks,reads,posts};}
}
