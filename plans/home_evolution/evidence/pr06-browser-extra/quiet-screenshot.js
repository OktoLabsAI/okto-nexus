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

  mode='idle';await page.setViewportSize({width:360,height:800});await reset();
  await page.getByRole('heading',{name:'What would you like to work on?',exact:true}).waitFor();
  const collapse=page.getByRole('button',{name:'Collapse navigation',exact:true});
  if(await collapse.count())await collapse.click();
  await page.getByRole('navigation').waitFor({state:'hidden'});
  await page.getByTestId('home-welcome').scrollIntoViewIfNeeded();
  await page.screenshot({path:'C:/Users/jpamb/AppData/Local/Temp/home-r1-extra-browser/postfix-idle-360-unobscured.png',fullPage:true});
  await page.unroute('**/api/v1/home/**',fixture);page.off('request',onRequest);page.off('pageerror',onError);
  return {screenshotOnly:true,navigationHidden:true};
}
