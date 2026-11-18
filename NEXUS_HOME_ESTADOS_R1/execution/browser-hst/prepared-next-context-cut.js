// PREPARED ONLY. Exact canonical IDs/cursors are supplied by the own fixture;
// no fake DTO, altered authority, or invocation accompanies this file.
async page=>{
 const cfg=__CONFIG__;
 if(cfg.window!=='POST_PERF_BROWSER_WINDOW_OPEN')throw Error('Explicit Root window required');
 const checks=[],requests=[],reads=[];const check=(id,ok,detail)=>{checks.push({id,ok,detail});if(!ok)throw Error(id);};
 page.on('request',r=>requests.push({method:r.method(),path:new URL(r.url()).pathname}));
 page.on('response',async r=>{if(r.request().method()==='GET'&&new URL(r.url()).pathname===cfg.relation_path){const item={at:Date.now(),status:r.status()};reads.push(item);if(r.status()===200){const raw=await r.json(),body=raw.data??raw;item.revision=body.revision;item.ids=body.items.map(x=>x.id??x.session_id??x.attention_id);}}});
 try{
  const dialog=page.getByRole('dialog',{name:'Activity detail'});await dialog.waitFor();
  await dialog.evaluate(e=>{window.__preparedContextNode=e;});
  const selection=await dialog.getByRole('combobox',{name:cfg.session_selector_label,exact:true}).inputValue();
  check('original-exact-session-selected',JSON.parse(selection).includes(cfg.session_id),true);
  // Host publishes a genuine new canonical related fact and acknowledges it
  // before this function runs. The retained next cursor must then be stale.
  await dialog.getByRole('button',{name:cfg.load_more_label,exact:true}).click();
  const id=cfg.session_id;
  for(let i=0;i<100&&!reads.some(x=>x.status===200&&x.at>(reads.find(y=>y.status===409)?.at??Infinity));i++)await page.waitForTimeout(100);
  check('real-cursor-conflict-then-current-reread',reads.some(x=>x.status===409)&&reads.some(x=>x.status===200&&x.at>(reads.find(y=>y.status===409)?.at??Infinity)),reads);
  check('same-panel-and-session-after-cursor-conflict',await dialog.evaluate(e=>e===window.__preparedContextNode)&&await dialog.getByRole('combobox',{name:cfg.session_selector_label,exact:true}).inputValue()===selection,id);
  check('single-modal-after-revalidation',await page.getByRole('dialog').count()===1,true);
  // Caller records network409 and subsequent current revision, disjoint IDs.
  await dialog.getByRole('button',{name:'Close modal',exact:true}).click();await dialog.waitFor({state:'hidden'});
  const historyURL=new URL(cfg.history_target_url);
  if(historyURL.origin!==new URL(cfg.url).origin||!historyURL.searchParams.has('home_target'))throw Error('Own canonical deep link required');
  await page.goto(historyURL.toString(),{waitUntil:'domcontentloaded'});await dialog.waitFor({timeout:10000});
  const original=page.url();
  await page.reload({waitUntil:'domcontentloaded'});await dialog.waitFor({timeout:10000});
  check('refresh-revalidates-same-session',(await dialog.innerText()).includes(id),id);
  await page.goBack();await dialog.waitFor({state:'hidden'});await page.goForward();
  await dialog.waitFor({timeout:10000});
  check('history-revalidates-same-full-target',new URL(page.url()).searchParams.get('home_target')===new URL(original).searchParams.get('home_target')&&(await dialog.innerText()).includes(id),true);
  return {status:'PREPARED_PHASE_RESULT',checks,requests,reads,required_followup:['Inspect IDs/current revisions and assert pages are replaced rather than mixed','Navigate a forged target in a separate own tab and assert denial/no preview/counter/no latest-session fallback','Close, open the exact canonical native question, choose0 and focus; Escape→Keep editing must preserve same DOM node/value/focus','Attempt projectB through real selector; cancel discard retains projectA and draft; explicit discard switches toB with no copied answer','Restore/open original exact question only if unexpired, then canonical logout clears protected data immediately'],limits:['This prepared function is one phase, not the complete F05/F14/I06 qualification','Host must publish canonical page change and independently assert409→current reread, not emulate a409 JSON response']};
 }catch(error){return {status:'FAIL_OR_INCOMPLETE',error:String(error),checks,requests,reads};}
}
