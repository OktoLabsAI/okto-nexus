async page => {
  const results=[],reads=[],mutations=[];
  const old=await page.evaluate(()=>JSON.parse(localStorage.getItem('home-r1-extra-results')));
  const target=old.checks[0].detail.target;
  const base='http://127.0.0.1:51697/';
  page.setDefaultTimeout(6000);
  const listener=r=>{const u=new URL(r.url());if(u.pathname==='/api/v1/home/target')reads.push(u.search);if(u.origin===new URL(base).origin&&!['GET','HEAD','OPTIONS'].includes(r.method()))mutations.push(r.method+' '+u.pathname);};
  page.on('request',listener);
  const assert=(v,m)=>{if(!v)throw Error(m);};
  const close=async()=>{if(await page.getByRole('dialog').count()){await page.keyboard.press('Escape');await page.getByRole('dialog').waitFor({state:'detached'});}};
  const navigate=async t=>{await close();const url=new URL(base);if(t)url.searchParams.set('home_target',JSON.stringify(t));await page.goto(url.href);await page.locator('[data-testid="operational-home"]').waitFor({state:'attached'});await page.locator('[aria-label="Work"]').waitFor({state:'attached'});};
  const run=async(name,fn)=>{try{results.push({name,status:'PASS',detail:await fn()});}catch(e){results.push({name,status:'FAIL',error:e.message});}};
  await run('F07 direct URL revalidates exact handoff despite modal hiding background roles',async()=>{
    const before=reads.length;await navigate(target);await page.getByRole('dialog').getByRole('heading',{name:'browser-handoff-0',exact:true}).waitFor();
    assert(reads.length>before,'No resolver GET');return {freshCanonicalGet:true,exactHandoff:true};
  });
  await run('F07 foreign workspace URL displays refusal without fallback or resolver GET',async()=>{
    const before=reads.length;await navigate({...target,workspace_id:'home-beta'});
    await page.getByRole('dialog').getByRole('alert').filter({hasText:'Home target is outside the current scope.'}).waitFor();
    assert(reads.length===before,'Wrong-scope resolver called');return {scopeRefused:true,noTargetGet:true};
  });
  await run('F07 missing exact record shows canonical unavailable without recent-record substitution',async()=>{
    await navigate({...target,handoff_id:'fixture-does-not-exist'});
    const alert=page.getByRole('dialog').getByRole('alert');await alert.waitFor();const text=await alert.innerText();
    assert(text.includes('no longer available'),'Unexpected canonical refusal: '+text);
    assert(await page.getByRole('dialog').getByRole('heading',{name:'browser-handoff-0',exact:true}).count()===0,'Fallback record displayed');
    return {canonicalError:text,noFallback:true};
  });
  await run('Light/dark via actual menu and 360px keyboard request-open-close preserves focus',async()=>{
    await navigate();await page.setViewportSize({width:360,height:800});
    await page.getByTestId('header-menu').click();await page.getByTestId('theme-toggle').click();
    const first=await page.evaluate(()=>document.documentElement.classList.contains('dark'));
    const trigger=page.getByRole('button',{name:'New request',exact:true});await trigger.focus();await page.keyboard.press('Enter');
    await page.getByRole('dialog',{name:'New request',exact:true}).waitFor();await page.keyboard.press('Escape');
    await page.getByRole('dialog').waitFor({state:'detached'});
    assert(await trigger.evaluate(el=>document.activeElement===el),'Keyboard focus lost');
    await page.screenshot({path:'C:/Users/jpamb/AppData/Local/Temp/home-r1-extra-browser/theme-first-360.png',fullPage:true});
    await page.getByTestId('header-menu').click();await page.getByTestId('theme-toggle').click();
    const second=await page.evaluate(()=>document.documentElement.classList.contains('dark'));
    const size=await page.evaluate(()=>({viewport:innerWidth,document:document.documentElement.scrollWidth}));
    assert(first!==second,'Theme unchanged');assert(size.document<=size.viewport,'Horizontal overflow');
    await page.screenshot({path:'C:/Users/jpamb/AppData/Local/Temp/home-r1-extra-browser/theme-second-360.png',fullPage:true});
    return {darkStates:[first,second],keyboardFocusRestored:true,...size};
  });
  page.off('request',listener);
  const result={checks:results,mutationAttempts:mutations,correction:'Earlier harness waited for background accessible Work region while legitimate modal made it inert; now waits only attachment. Theme button is inside header menu, now opened explicitly. No product changes.'};
  await page.evaluate(v=>localStorage.setItem('home-r1-extra-delta',JSON.stringify(v)),result);
  return result;
}
