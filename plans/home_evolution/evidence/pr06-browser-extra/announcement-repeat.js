async page => {
  await page.setViewportSize({width:1440,height:1000});await page.goto('http://127.0.0.1:51697/');
  await page.getByRole('heading',{name:'Review the integration',exact:true}).waitFor();
  let serial=1;
  const routeFn=async route=>{const response=await route.fetch();const envelope=await response.json();const d=envelope.data;
    d.work={...d.work,revision:'announcement-'+serial,items:[...d.work.items,{...d.work.items[0],id:'new-announcement-'+serial,title:'New fixture '+serial}]};
    await route.fulfill({response,json:envelope});};
  await page.route('**/api/v1/home/overview?*',routeFn);
  await page.evaluate(()=>{window.__announce=[];const e=document.querySelector('[aria-live="polite"][aria-atomic="true"]');window.__aObserver=new MutationObserver(()=>window.__announce.push(e.textContent));window.__aObserver.observe(e,{childList:true,subtree:true,characterData:true});});
  const refresh=async()=>{const response=page.waitForResponse(r=>r.url().includes('/api/v1/home/overview')&&r.status()===200);await page.evaluate(()=>window.dispatchEvent(new Event('focus')));await response;};
  await refresh();await page.waitForFunction(()=>window.__announce.length===1);serial=2;await refresh();
  // The component batches on a real 2s timer. Observe a second distinct burst
  // after the first has committed; do not fake accessibility speech.
  await page.waitForTimeout(2500);
  const result=await page.evaluate(()=>({domAnnouncements:window.__announce,liveText:document.querySelector('[aria-live="polite"][aria-atomic="true"]').textContent,secondWorkVisible:document.body.textContent.includes('New fixture 2')}));
  await page.evaluate(()=>window.__aObserver.disconnect());await page.unroute('**/api/v1/home/overview?*',routeFn);
  result.status=result.secondWorkVisible&&result.domAnnouncements.length<2?'REPEATED_UPDATE_NOT_ANNOUNCED':'PASS';
  await page.evaluate(v=>localStorage.setItem('home-r1-repeat-announcement',JSON.stringify(v)),result);return result;
}
