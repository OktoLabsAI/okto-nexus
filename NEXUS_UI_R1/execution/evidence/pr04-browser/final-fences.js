async page=>{
  const cfg=__FIXTURE_CONFIG__,checks=[],responses=[],requests=[],errors=[];
  page.on('response',r=>responses.push({url:r.url(),status:r.status()}));
  page.on('request',r=>requests.push({url:r.url(),method:r.method()}));
  page.on('pageerror',e=>errors.push(e.message));
  page.on('dialog',d=>{if(d.type()==='beforeunload')void d.accept();});
  const check=(name,ok,data={})=>{checks.push({name,status:ok?'PASS':'FAIL',...data});if(!ok)throw Error(name);};
  try{
    await page.setViewportSize({width:1440,height:1100});await page.goto(cfg.url);
    await page.getByTestId('home-follow-up').waitFor();
    const allResponse=page.waitForResponse(r=>r.url().includes('/home/entries?')&&r.url().includes('quick=all')&&r.status()===200);
    await page.getByRole('group',{name:'Follow-up filter',exact:true}).getByRole('button',{name:'All',exact:true}).click();
    const groups=(await(await allResponse).json()).data.items;
    const pair=groups.flatMap(g=>g.children.map(e=>({g,e}))).find(({e})=>e.kind==='session'&&e.target.session_id===cfg.identities.no_turn_session);
    const group=page.locator(`[data-home-group="${pair.g.id}"]`),expand=group.getByRole('button',{name:'Expand',exact:true});
    if(await expand.count())await expand.click();
    await group.locator(`[data-home-entry="${pair.e.id}"] [data-home-entry-open]`).click();
    await page.getByRole('region',{name:'Session execution output',exact:true}).getByText(cfg.identities.no_turn_session,{exact:true}).waitFor();
    const targetURL=page.url();await page.goBack();
    await page.getByTestId('home-detail').waitFor({state:'detached'});
    check('browser Back closes exact passive context without replacement',!page.url().includes('home_target=')&&await page.getByRole('dialog').count()===0,{targetURL});
    await page.getByRole('button',{name:'New request',exact:true}).click();
    await page.getByRole('textbox',{name:'Message',exact:true}).fill('unsent history guard probe');
    await page.evaluate(()=>history.pushState(null,'',location.href));
    await page.goBack();
    await page.getByText('Discard unsaved changes?',{exact:true}).waitFor();
    await page.getByRole('button',{name:'Keep editing',exact:true}).click();
    check('browser Back dirty guard preserves real composer draft',(await page.getByRole('textbox',{name:'Message',exact:true}).inputValue())==='unsent history guard probe');
    await page.getByRole('button',{name:'Close modal',exact:true}).click();
    await page.getByRole('button',{name:'Discard changes',exact:true}).click();
    await page.getByTestId('home-detail').waitFor({state:'detached'});
    const before=await page.evaluate(()=>({innerWidth,ratio:devicePixelRatio}));
    for(let i=0;i<4;i++)await page.keyboard.press('Control++');
    const after=await page.evaluate(()=>({innerWidth,ratio:devicePixelRatio}));
    checks.push({name:'native 200% browser zoom',status:'NOT_RUN',before,after,reason:'Keyboard shortcut did not establish a verified native200% zoom level; viewport/CSS are not substituted.'});
    await page.keyboard.press('Control+0');
    await page.setExtraHTTPHeaders({'x-ui04-fixture-actor':'other'});
    const denied=page.waitForResponse(r=>r.url().includes('/api/v1/home/entries?')&&r.status()===403);
    await page.getByRole('button',{name:'Refresh',exact:true}).click();
    await denied;
    await page.getByText('Operator access is required. Protected Home data has been cleared.',{exact:true}).waitFor();
    check('canonical other-agent403 clears protected Home entries',await page.locator('[data-home-entry]').count()===0&&await page.getByRole('dialog').count()===0);
    await page.screenshot({path:`${cfg.outputDirectory}/real403-home-cleared.png`,fullPage:true});
    check('fence probe has no mutations or page exceptions',!requests.some(r=>!['GET','HEAD','OPTIONS'].includes(r.method))&&errors.length===0,{errors});
    return{status:'PASS',checks,responses,requests,errors,scope:'Home read denial after passive panel closed; does not qualify live viewer403 or native AT/zoom'};
  }catch(e){await page.screenshot({path:`${cfg.outputDirectory}/fences-failure.png`,fullPage:true});return{status:'FAIL',message:e.message,checks,responses,requests,errors};}
  finally{await page.setExtraHTTPHeaders({});await page.goto('about:blank');}
}
