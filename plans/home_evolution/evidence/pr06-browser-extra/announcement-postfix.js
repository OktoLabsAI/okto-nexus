async page => {
  await page.setViewportSize({width:1440,height:1000});await page.goto('http://127.0.0.1:51697/');
  await page.getByRole('heading',{name:'Review the integration',exact:true}).waitFor();
  let serial=1;
  const routeFn=async route=>{const response=await route.fetch();const envelope=await response.json();const d=envelope.data;
    d.work={...d.work,revision:'announcement-'+serial,items:[...d.work.items,{...d.work.items[0],id:'new-announcement-'+serial,title:'New fixture '+serial}]};
    await route.fulfill({response,json:envelope});};
  await page.route('**/api/v1/home/overview?*',routeFn);
  await page.evaluate(()=>{window.__announce=[];const e=document.querySelector('[aria-live="polite"][aria-atomic="true"]');window.__aObserver=new MutationObserver(()=>window.__announce.push({text:e.textContent,at:performance.now()}));window.__aObserver.observe(e,{childList:true,subtree:true,characterData:true});});
  const refresh=async()=>{const response=page.waitForResponse(r=>r.url().includes('/api/v1/home/overview')&&r.status()===200);await page.evaluate(()=>window.dispatchEvent(new Event('focus')));await response;};
  await refresh();await page.waitForFunction(()=>window.__announce.filter(x=>x.text).length===1);
  serial=2;await refresh();await page.waitForFunction(()=>window.__announce.filter(x=>x.text).length===2);
  const bursts=await page.evaluate(()=>({changes:window.__announce,secondWorkVisible:document.body.textContent.includes('New fixture 2')}));
  if(!bursts.secondWorkVisible||bursts.changes.filter(x=>x.text).length!==2)throw Error('Separate bursts not announced exactly once each');
  serial=3;await refresh();
  await page.getByRole('combobox',{name:'Workspace scope'}).selectOption('home-beta');
  await page.getByRole('region',{name:'Work',exact:true}).getByRole('heading',{name:'Lyra: independent request',exact:true}).waitFor();
  await page.waitForTimeout(2500);
  const afterScope=await page.evaluate(()=>({liveText:document.querySelector('[aria-live="polite"][aria-atomic="true"]').textContent,changes:window.__announce}));
  if(afterScope.liveText!=='')throw Error('Prior generation announcement survived or fired into new workspace');
  if(afterScope.changes.filter(x=>x.text).length!==2)throw Error('A cancelled generation timer announced old content');
  await page.evaluate(()=>window.__aObserver.disconnect());await page.unroute('**/api/v1/home/overview?*',routeFn);
  const result={status:'PASS_DOM_ONLY',bursts,afterScope,checks:{twoDistinctBurstsAnnounced:true,exactlyTwoNonemptyAnnouncements:true,pendingTimerCancelledOnWorkspaceChange:true},
    speechOrHumanScreenReaderTested:false,scripts:await page.evaluate(()=>[...document.scripts].map(x=>x.src).filter(Boolean))};
  await page.evaluate(v=>localStorage.setItem('home-r1-postfix-announcement',JSON.stringify(v)),result);return result;
}
