async (page) => {
  const checks=[], mutations=[], errors=[], targetReads=[];
  const base='http://127.0.0.1:51697/';
  const assert=(ok,why)=>{if(!ok)throw Error(why);};
  page.setDefaultTimeout(6000);
  const dialogListener=dialog=>dialog.type()==='beforeunload'?dialog.accept():dialog.dismiss();
  page.on('dialog',dialogListener);
  const requestListener=r=>{const u=new URL(r.url());if(u.origin===new URL(base).origin){if(!['GET','HEAD','OPTIONS'].includes(r.method()))mutations.push({method:r.method(),path:u.pathname});if(u.pathname==='/api/v1/home/target')targetReads.push(u.search);}};
  const errorListener=e=>errors.push(e.message);
  page.on('request',requestListener);page.on('pageerror',errorListener);
  const run=async(name,fn)=>{try{checks.push({name,status:'PASS',detail:await fn()});}catch(e){checks.push({name,status:'FAIL',error:e.message.split('\n')[0]});}};
  const reset=async(url=base)=>{await page.goto(url);await page.getByTestId('operational-home').waitFor();await page.getByRole('region',{name:'Work',exact:true}).waitFor();};
  let exact,deep;
  await run('F07 real back and forward preserve exact canonical handoff target',async()=>{
    await reset();await page.getByRole('button',{name:'Inspect Review the integration',exact:true}).click();
    await page.getByRole('dialog').getByRole('heading',{name:'browser-handoff-0',exact:true}).waitFor();
    deep=page.url();exact=JSON.parse(new URL(deep).searchParams.get('home_target'));
    await page.goBack();await page.getByRole('dialog').waitFor({state:'detached'});
    await page.goForward();await page.getByRole('dialog').getByRole('heading',{name:'browser-handoff-0',exact:true}).waitFor();
    assert(new URL(page.url()).searchParams.get('home_target')===JSON.stringify(exact),'History changed canonical target');
    await page.keyboard.press('Escape');await page.getByRole('dialog').waitFor({state:'detached'});
    return {target:exact,backClosed:true,forwardReopened:true};
  });
  await run('F07 deep-link reload resolves the exact record through a fresh canonical GET',async()=>{
    assert(deep,'No initial exact target'); const count=targetReads.length;await reset(deep);
    await page.getByRole('dialog').getByRole('heading',{name:'browser-handoff-0',exact:true}).waitFor();
    assert(targetReads.length>count,'Deep-link did not revalidate');
    await page.keyboard.press('Escape');return {freshTargetGet:true};
  });
  await run('F07 malformed URL reference is rejected without target fetch',async()=>{
    const count=targetReads.length;const url=new URL(base);url.searchParams.set('home_target',JSON.stringify({kind:'arbitrary',url:'https://invalid.example/'}));
    await reset(url.href);await page.getByText('The saved detail reference is invalid. No record was selected.',{exact:true}).waitFor();
    assert(await page.getByRole('dialog').count()===0,'Malformed reference opened drawer');assert(targetReads.length===count,'Malformed target reached resolver');
    return {noDrawer:true,noTargetFetch:true};
  });
  await run('F07 foreign workspace target refuses instead of selecting another record',async()=>{
    assert(exact,'Missing selected target');const count=targetReads.length;const url=new URL(base);url.searchParams.set('home_target',JSON.stringify({...exact,workspace_id:'home-beta'}));
    await reset(url.href);await page.getByRole('dialog').getByText('Home target is outside the current scope.',{exact:false}).waitFor();
    assert(await page.getByRole('dialog').getByRole('heading',{name:'browser-handoff-0',exact:true}).count()===0,'Wrong scope displayed target');
    assert(targetReads.length===count,'Wrong workspace reached resolver');await page.keyboard.press('Escape');
    return {scopeRefused:true,noFallback:true};
  });
  await run('F07 missing exact record remains unavailable with canonical404 and no latest fallback',async()=>{
    const url=new URL(base);url.searchParams.set('home_target',JSON.stringify({...exact,handoff_id:'fixture-does-not-exist'}));
    const response=page.waitForResponse(r=>r.url().includes('/api/v1/home/target')&&r.status()===404).catch(()=>null);
    await reset(url.href);assert(await response,'Missing canonical404 response');
    const dialog=page.getByRole('dialog');await dialog.getByRole('alert').waitFor();
    const text=await dialog.innerText();assert(!text.includes('browser-handoff-0'),'Missing record fell back');
    await page.keyboard.press('Escape');return {canonicalStatus:404,dialogText:text.slice(0,300)};
  });
  let mode='none',addition=0;
  const fixture=async route=>{
    const url=new URL(route.request().url());
    if(route.request().method()!=='GET'||!['/api/v1/home/overview','/api/v1/home/agents','/api/v1/home/activity'].includes(url.pathname))return route.fallback();
    const response=await route.fetch();const envelope=await response.json();const data=envelope.data;
    if(!data||mode==='none')return route.fulfill({response});
    const empty=s=>({...s,status:'ready',items:[],total:0,total_is_exact:true,has_more:false,next_cursor:null,revision:'fixture-'+mode+'-'+addition});
    const agent={agent_id:'A',name:'A',workspace_ids:['home-alpha'],presence:'online',connectivity:'connected',activity:'not_reported'};
    if(url.pathname==='/api/v1/home/overview'){
      if(mode==='empty'||mode==='idle'){
        for(const key of ['work','attention','results','agents'])data[key]=empty(data[key]);
        if(mode==='idle'){data.agents.items=[agent];data.agents.total=1;}
        for(const key of ['running','waiting_start','needs_you','results'])data.summary[key]={...data.summary[key],value:0,total_is_exact:true};
      }else if(mode==='announce'){
        data.work={...data.work,items:[...data.work.items,{...data.work.items[0],id:'announced-fixture-'+addition,title:'Fixture newly available work'}],revision:'announce-'+addition,total:data.work.total+1};
      }
    }else if(url.pathname==='/api/v1/home/agents')Object.assign(data,empty(data),{items:mode==='idle'?[agent]:[],total:mode==='idle'?1:0});
    else if(mode==='empty'||mode==='idle')Object.assign(data,empty(data));
    return route.fulfill({response,json:envelope});
  };
  await page.route('**/api/v1/home/**',fixture);
  await run('F01 empty installation exposes setup action without advanced setup forms',async()=>{
    mode='empty';await reset();await page.getByRole('button',{name:'Set up an agent',exact:true}).waitFor();
    const text=await page.getByTestId('operational-home').innerText();
    assert(!/API key|Client secret|Harness root/.test(text),'Advanced configuration leaked into empty Home');
    await page.screenshot({path:'C:/Users/jpamb/AppData/Local/Temp/home-r1-extra-browser/empty.png',fullPage:true});
    return {fixtureOverride:'GET Home overview/agents/activity only',setupAction:true,advancedForm:false,regionCount:await page.getByTestId('operational-home').getByRole('region').count()};
  });
  await run('F02 one connected idle agent foregrounds request rather than six empty panels',async()=>{
    mode='idle';await reset();await page.getByRole('region',{name:'Agents',exact:true}).getByText('A',{exact:true}).waitFor();
    await page.getByRole('button',{name:'New request',exact:true}).waitFor();
    const regions=await page.getByTestId('operational-home').getByRole('region').allTextContents();
    await page.screenshot({path:'C:/Users/jpamb/AppData/Local/Temp/home-r1-extra-browser/one-idle.png',fullPage:true});
    const emptyPanels=regions.filter(t=>/No matching|No recent|Disabled|No external/.test(t));
    return {requestAction:true,regions:regions.length,emptyPanels:emptyPanels.length,uxAssessmentRequired:emptyPanels.length>=4,
      note:'No numeric acceptance threshold invented; Root should assess whether the empty-panel layout meets literal F02.'};
  });
  await run('H02 live-region batches newly added IDs into one useful DOM announcement',async()=>{
    mode='none';await reset();
    await page.locator('[aria-live="polite"][aria-atomic="true"]').waitFor({state:'attached'});
    await page.evaluate(()=>{window.__homeAnnouncementChanges=[];const el=document.querySelector('[aria-live="polite"][aria-atomic="true"]');window.__homeAnnouncementObserver=new MutationObserver(()=>window.__homeAnnouncementChanges.push({text:el.textContent,at:performance.now()}));window.__homeAnnouncementObserver.observe(el,{childList:true,characterData:true,subtree:true});});
    mode='announce';addition=1;
    const refresh=async()=>{const response=page.waitForResponse(r=>r.url().includes('/api/v1/home/overview')&&r.status()===200);await page.evaluate(()=>window.dispatchEvent(new Event('focus')));await response;};
    await refresh();addition=2;await refresh();
    await page.waitForFunction(()=>document.querySelector('[aria-live="polite"][aria-atomic="true"]').textContent.includes('New work'));
    const changes=await page.evaluate(()=>window.__homeAnnouncementChanges);
    assert(changes.length===1,'Burst generated '+changes.length+' announcements');
    assert(changes[0].text==='Home updated. New work, attention or results are available.','Unexpected announcement');
    await page.evaluate(()=>window.__homeAnnouncementObserver.disconnect());
    return {domChanges:changes.length,text:changes[0].text,speechOrHumanAssistiveTechnologyTested:false};
  });
  mode='none';await reset();
  await run('Light/dark variants and 360px main keyboard path retain labels and focus',async()=>{
    await page.setViewportSize({width:360,height:800});
    // Theme toggle is the product action; no fabricated CSS screenshots.
    await page.getByTestId('theme-toggle').click();
    const first=await page.evaluate(()=>document.documentElement.classList.contains('dark'));
    await page.getByRole('button',{name:'New request',exact:true}).focus();await page.keyboard.press('Enter');
    await page.getByRole('dialog',{name:'New request',exact:true}).waitFor();await page.keyboard.press('Escape');
    await page.getByRole('dialog').waitFor({state:'detached'});
    assert(await page.getByRole('button',{name:'New request',exact:true}).evaluate(el=>document.activeElement===el),'Keyboard close lost trigger');
    await page.screenshot({path:'C:/Users/jpamb/AppData/Local/Temp/home-r1-extra-browser/theme-first-360.png',fullPage:true});
    await page.getByTestId('theme-toggle').click();const second=await page.evaluate(()=>document.documentElement.classList.contains('dark'));
    assert(first!==second,'Theme did not change');
    const size=await page.evaluate(()=>({viewport:innerWidth,document:document.documentElement.scrollWidth}));assert(size.document<=size.viewport,'360px overflow');
    await page.screenshot({path:'C:/Users/jpamb/AppData/Local/Temp/home-r1-extra-browser/theme-second-360.png',fullPage:true});
    return {darkStates:[first,second],keyboardOpenClose:true,focusRestored:true,...size};
  });
  await page.unroute('**/api/v1/home/**',fixture);
  page.off('request',requestListener);page.off('pageerror',errorListener);page.off('dialog',dialogListener);
  const result={status:checks.some(c=>c.status==='FAIL')?'FINDINGS':'PASS_SCOPED',checks,mutationAttempts:mutations,pageErrors:errors,
    environment:'Isolated CLI session home-r1-extra; read-only synthetic HTTP fixture51697; no provider/runtime/server mutation',
    limitations:['F01/F02/announcement are explicit GET response fixtures, not real empty installation or native producers.','No native question/decision or two-tab approval fake was constructed.','aria-live checks DOM only, not screen-reader speech.','No true 200% browser zoom claim.']};
  await page.evaluate(value=>localStorage.setItem('home-r1-extra-results',JSON.stringify(value)),result);
  return result;
}
