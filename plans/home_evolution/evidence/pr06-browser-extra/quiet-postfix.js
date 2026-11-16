async page => {
  const checks=[], mutations=[], errors=[]; let mode='empty';
  const assert=(ok,message)=>{if(!ok)throw Error(message);};
  const onRequest=r=>{if(new URL(r.url()).origin==='http://127.0.0.1:51697'&&!['GET','HEAD','OPTIONS'].includes(r.method()))mutations.push({method:r.method(),path:new URL(r.url()).pathname});};
  const onError=e=>errors.push(e.message);page.on('request',onRequest);page.on('pageerror',onError);
  const empty=s=>({...s,status:'ready',items:[],total:0,total_is_exact:true,has_more:false,next_cursor:null,revision:'quiet-fixture-'+mode});
  const agent={agent_id:'A',name:'A',workspace_ids:['home-alpha'],presence:'online',connectivity:'connected',activity:'not_reported'};
  const fixture=async route=>{
    const path=new URL(route.request().url()).pathname;
    if(route.request().method()!=='GET'||!['/api/v1/home/overview','/api/v1/home/agents','/api/v1/home/activity'].includes(path))return route.fallback();
    const response=await route.fetch();const envelope=await response.json();const d=envelope.data;
    if(path.endsWith('/overview')){
      for(const key of ['work','attention','results','agents'])d[key]=empty(d[key]);
      if(mode!=='empty'){d.agents.items=[agent];d.agents.total=1;}
      for(const key of ['running','waiting_start','needs_you','results'])d.summary[key]={...d.summary[key],value:0,total_is_exact:true};
      if(['partial','unavailable','disabled'].includes(mode))d.work={...d.work,status:mode,total:null,total_is_exact:false,reason_code:'FIXTURE_'+mode.toUpperCase()};
    }else if(path.endsWith('/agents'))Object.assign(d,empty(d),{items:mode==='empty'?[]:[agent],total:mode==='empty'?0:1});
    else Object.assign(d,empty(d));
    return route.fulfill({response,json:envelope});
  };
  await page.unroute('**/api/v1/home/**');
  await page.route('**/api/v1/home/**',fixture);
  const reset=async()=>{await page.goto('http://127.0.0.1:51697/');await page.getByTestId('operational-home').waitFor();};
  await page.setViewportSize({width:1440,height:1000});await reset();
  await page.getByRole('heading',{name:'Set up your first agent',exact:true}).waitFor();
  const home=page.getByTestId('operational-home');
  assert(await home.locator('[aria-label="Operational summary"]').count()===0,'Empty Home retains zero grid');
  assert(await home.getByRole('region',{name:/^(Work|Needs you|Results|Agents)$/}).count()===0,'Empty Home retains empty panels');
  await page.getByText('External reports are disabled.',{exact:true}).waitFor();
  assert(!/API key|Client secret|Harness root/.test(await home.innerText()),'Advanced form on welcome');
  await page.screenshot({path:'C:/Users/jpamb/AppData/Local/Temp/home-r1-extra-browser/postfix-empty.png',fullPage:true});
  checks.push({id:'F01',status:'PASS_DOM_FIXTURE',setupCTA:true,noZeroGrid:true,noEmptyPrimaryPanels:true,disabledExternalExplicit:true});
  mode='idle';await reset();await page.getByRole('heading',{name:'What would you like to work on?',exact:true}).waitFor();
  await home.getByRole('region',{name:'Agents',exact:true}).getByText('A',{exact:true}).waitFor();
  assert(await home.locator('[aria-label="Operational summary"]').count()===0,'Idle Home retains zero grid');
  assert(await home.getByRole('region',{name:/^(Work|Needs you|Results)$/}).count()===0,'Idle Home retains empty primary panels');
  const button=page.getByTestId('home-welcome').getByRole('button',{name:'New request',exact:true});
  await button.focus();await page.keyboard.press('Enter');await page.getByRole('dialog',{name:'New request',exact:true}).waitFor();await page.keyboard.press('Escape');await page.getByRole('dialog').waitFor({state:'detached'});
  assert(await button.evaluate(el=>el===document.activeElement),'Quiet CTA did not regain focus');
  await page.setViewportSize({width:360,height:800});
  const width=await page.evaluate(()=>({viewport:innerWidth,document:document.documentElement.scrollWidth}));assert(width.document<=width.viewport,'Quiet layout overflows360');
  await page.screenshot({path:'C:/Users/jpamb/AppData/Local/Temp/home-r1-extra-browser/postfix-idle-360.png',fullPage:true});
  checks.push({id:'F02',status:'PASS_DOM_FIXTURE',requestCTA:true,workerCard:true,noZeroGrid:true,noEmptyPrimaryPanels:true,keyboardDrawerFocus:true,...width});
  for(mode of ['partial','unavailable','disabled']){
    await reset();const work=home.getByRole('region',{name:'Work',exact:true});await work.waitFor();
    await work.getByText('Total unknown',{exact:true}).waitFor();
    assert(await page.getByTestId('home-welcome').count()===0,mode+' incorrectly shows quiet welcome');
    const text=await work.innerText();assert((text.toLowerCase().includes(mode)||text.includes('Out of date · last authorized snapshot')),mode+' missing explicit state');
    checks.push({id:'quiet-guard-'+mode,status:'PASS_DOM_FIXTURE',text});
  }
  await page.unroute('**/api/v1/home/**',fixture);page.off('request',onRequest);page.off('pageerror',onError);
  const result={checks,mutationAttempts:mutations,pageErrors:errors,scripts:await page.evaluate(()=>[...document.scripts].map(x=>x.src).filter(Boolean)),limits:['GET response fixtures only; backend bootstrap/operator exclusion qualified separately by actual ASGI test.','No setup, native work or producer was executed.']};
  assert(mutations.length===0&&errors.length===0,'Unexpected mutation or browser error');
  await page.evaluate(x=>localStorage.setItem('home-r1-postfix-quiet',JSON.stringify(x)),result);return result;
}
