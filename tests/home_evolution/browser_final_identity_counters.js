// Focused real-browser supplement to browser_final_identity.js. Synthetic GET only.
async (page) => {
  page.setDefaultTimeout(7000);
  await page.addInitScript(() => {
    if (!['http:','https:'].includes(location.protocol)) return;
    localStorage.setItem('okto-nexus-home-operational','enabled');
    localStorage.setItem('okto.nexus.onboarding.completed.v1','true');
    localStorage.setItem('okto-nexus:metrics-opt-in-prompt-dismissed:1.0.0','test');
  });
  await page.goto('http://127.0.0.1:60183');
  const scope=page.getByRole('combobox',{name:'Workspace scope'});
  await scope.selectOption('home-alpha');
  await page.getByRole('heading',{name:'Review the integration',exact:true}).waitFor();
  const counters=()=>page.locator('[aria-label="Operational summary"]').innerText();
  const aCounters=await counters();
  let release,captured,finished,held=false,lateOutcome;
  const capturedPromise=new Promise(r=>captured=r),done=new Promise(r=>finished=r),barrier=new Promise(r=>release=r);
  const handler=async route=>{
    const u=new URL(route.request().url());
    if(held||u.searchParams.get('workspace_id')!=='home-alpha')return route.fallback();
    held=true;const response=await route.fetch();captured();await barrier;
    try{await route.fulfill({response});lateOutcome='fulfilled after B form';}
    catch{lateOutcome='aborted obsolete request';}
    finally{finished();}
  };
  const mutations=[];const onRequest=r=>{if(!['GET','HEAD','OPTIONS'].includes(r.method()))mutations.push(r.method());};
  page.on('request',onRequest);
  await page.route('**/api/v1/home/overview?*',handler);
  try{
    await page.getByRole('button',{name:'Refresh Home',exact:true}).click();await capturedPromise;
    await scope.selectOption('home-beta');
    await page.getByRole('heading',{name:'Lyra: independent request',exact:true}).waitFor();
    const bBefore=await counters();
    if(aCounters===bBefore)throw Error('Fixture counters must distinguish A from B');
    await page.getByRole('button',{name:'New request',exact:true}).click();
    const message=page.getByRole('textbox',{name:'Message',exact:true});
    await message.fill('B-only counter barrier draft.');await message.focus();
    await message.evaluate(e=>{e.dataset.counterProbe='same';e.setSelectionRange(2,8);});
    release();await done;
    await page.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));
    const bAfter=await counters();
    const form=await message.evaluate(e=>({value:e.value,same:e.dataset.counterProbe==='same',focused:e===document.activeElement,selection:[e.selectionStart,e.selectionEnd]}));
    if(bBefore!==bAfter)throw Error('Late A changed B counters');
    if(await scope.inputValue()!=='home-beta')throw Error('Late A changed B scope');
    if(await page.getByRole('heading',{name:'Review the integration',exact:true}).count())throw Error('Late A work leaked');
    if(!form.same||!form.focused||form.selection.join(',')!=='2,8'||form.value!=='B-only counter barrier draft.')throw Error('Late A changed B form');
    if(mutations.length)throw Error('Unexpected mutation');
    return {status:'PASS',scenario:'HOME-T-A06',aCounters,bCountersBeforeLateA:bBefore,bCountersAfterLateA:bAfter,lateOutcome,form,oldWorkAbsent:true,mutationRequests:mutations,bundle:await page.locator('script[src]').evaluateAll(ns=>ns.map(n=>n.getAttribute('src')))};
  }finally{
    release();await done;await page.unroute('**/api/v1/home/overview?*',handler);page.off('request',onRequest);
    if(await page.getByRole('dialog').count()){
      await page.keyboard.press('Escape');await page.getByRole('button',{name:'Discard changes',exact:true}).click();
      await page.getByRole('dialog').waitFor({state:'detached'});
    }
    await page.goto('about:blank');
  }
}
