// Playwright CLI run-code function. PREPARED ONLY: no server/profile allocated.
async (page) => {
  const cfg = {preparedOnly:true}; // Replace only with future public HTTP READY.
  if(cfg.preparedOnly || cfg.window!=='PERF_DOM_WINDOW_OPEN' || cfg.kind!=='HST_LARGE_DOM_PERFORMANCE_FIXTURE' || cfg.ready!==true)
    throw Error('Prepared only; require Root window and canonical owned HTTP READY.');
  if(cfg.presentation_version!==2 || cfg.workspace_id!=='hst-perf' ||
     cfg.counts?.registered_connections!==100 || cfg.counts?.open_activities!==1000 || cfg.counts?.native_events!==100000)
    throw Error('Wrong synthetic workload; never adapt dataset to pass the gate.');
  const seedMillis=Date.parse(cfg.seed_clock);
  if(!Number.isFinite(seedMillis))throw Error('Missing original controlled clock.');
  const origin=new URL(cfg.origin);
  if(origin.protocol!=='http:' || origin.hostname!=='127.0.0.1')throw Error('Own loopback only.');
  const requests=[],responses=[],errors=[];
  await page.setViewportSize({width:1440,height:1100});
  const cdp=await page.context().newCDPSession(page);
  await cdp.send('Network.enable');
  await cdp.send('Network.setCacheDisabled',{cacheDisabled:true});
  await page.addInitScript(({seedMillis,workspace})=>{
    // PERFORMANCE_FIXTURE wall time only. Monotonic timing and timers are real.
    const NativeDate=window.Date, anchor=performance.now();
    const wallNow=()=>seedMillis+performance.now()-anchor;
    function FixtureDate(...args){
      if(!new.target)return new NativeDate(wallNow()).toString();
      return Reflect.construct(NativeDate,args.length?args:[wallNow()],new.target);
    }
    Object.setPrototypeOf(FixtureDate,NativeDate);
    FixtureDate.prototype=NativeDate.prototype;
    FixtureDate.now=wallNow;
    window.Date=FixtureDate;
    localStorage.setItem('okto-nexus-home-operational','enabled');
    localStorage.setItem('okto-nexus-workspace',workspace);
    localStorage.setItem('okto-nexus:metrics-opt-in-prompt-dismissed:1.0.0',new Date().toISOString());
    window.__hstLargeDOM={candidates:[],clockOverride:'PERFORMANCE_FIXTURE_DATE_ONLY',seedMillis};
    const visible=e=>Boolean(e&&e.getClientRects().length);
    const capture=()=>{
      const board=document.querySelector('[data-testid="home-board"]');
      const summary=document.querySelector('[data-testid="home-summary-cards"]');
      const project=document.querySelector('[data-testid="home-project-card"]');
      if(!visible(board)||!visible(summary)||!visible(project))return;
      const columns=[...board.querySelectorAll('[data-home-column]')];
      const harnesses=[...board.querySelectorAll('[data-home-harness]')];
      if(columns.length!==3 || !columns.every(visible) || !harnesses.length)return;
      const labels=columns.map(e=>e.getAttribute('data-home-column'));
      if(JSON.stringify([...labels].sort())!==JSON.stringify(['active','needs_you','results'].sort()))return;
      if(/Loading (column|activity)|Last known:|Previous snapshot/i.test(board.innerText+'\n'+summary.innerText))return;
      if(window.__hstLargeDOM.candidates.length>=200)return;
      window.__hstLargeDOM.candidates.push({at:performance.now(),timeOrigin:performance.timeOrigin,
        cards:harnesses.map(e=>({id:e.getAttribute('data-home-harness'),column:e.closest('[data-home-column]').getAttribute('data-home-column')})),
        summary:summary.innerText,project:project.innerText,headers:columns.map(e=>e.querySelector('h2,h3')?.textContent??'')});
    };
    new MutationObserver(capture).observe(document,{subtree:true,childList:true,characterData:true,attributes:true,attributeFilter:['aria-busy']});
    document.addEventListener('DOMContentLoaded',capture);
  },{seedMillis,workspace:cfg.workspace_id});
  page.on('pageerror',e=>errors.push(String(e)));
  page.on('request',r=>{
    const u=new URL(r.url());
    if(u.origin===origin.origin)requests.push({method:r.method(),path:u.pathname});
  });
  page.on('response',async r=>{
    const u=new URL(r.url());
    if(u.origin!==origin.origin || u.pathname!=='/api/v1/home/harness-board')return;
    try{
      const body=await r.json(), data=body.data??body;
      responses.push({status:r.status(),version:data.presentation_version,server_id:data.server_id,scope:data.scope,
        source_status:data.source_status,status_value:data.status,inventory:data.inventory,
        summary:data.operational_summary,
        cards:Object.entries(data.columns??{}).flatMap(([column,s])=>(s.items??[]).filter(i=>i.kind==='harness').map(i=>({id:i.id,column}))),
        bytes:Number(r.headers()['content-length']??0)||null});
    }catch(e){responses.push({status:r.status(),parseError:String(e)});}
  });
  const hostAnchor=Date.now();
  await page.goto(cfg.origin,{waitUntil:'domcontentloaded'});
  await page.waitForFunction(()=>window.__hstLargeDOM?.candidates.length>0,undefined,{timeout:30000});
  // Host-side response validation is outside the captured DOM timestamp.
  const deadline=Date.now()+30000;
  while(!responses.length&&Date.now()<deadline)await new Promise(resolve=>setTimeout(resolve,20));
  const response=responses[0];
  if(!response || response.status!==200 || response.version!==2 || response.server_id!==cfg.server_id ||
     response.scope?.workspace_id!==cfg.workspace_id || response.inventory?.registered_harnesses?.value!==100)
    throw Error('Canonical large workload response absent; not a useful-DOM timing.');
  if(!['ready','partial'].includes(response.status_value)||!Object.entries(response.source_status??{}).every(([k,v])=>v==='ready'||k==='external'&&v==='disabled'))
    throw Error('Required source failed; timing is NOT_QUALIFIED.');
  const captured=await page.evaluate(()=>window.__hstLargeDOM);
  const ordered=v=>JSON.stringify([...v].sort((a,b)=>a.column.localeCompare(b.column)||a.id.localeCompare(b.id)));
  const useful=captured.candidates.find(c=>ordered(c.cards)===ordered(response.cards));
  if(!useful || errors.length || requests.some(r=>!['GET','HEAD','OPTIONS'].includes(r.method)))
    throw Error('Matching rendered canonical cards/read-only navigation proof absent.');
  return {status:'SINGLE_LARGE_DOM_MEASUREMENT',workload:cfg.counts,seed_clock:cfg.seed_clock,
    clockOverride:captured.clockOverride,performanceClock:'real untouched performance.now',hostAnchor,
    useful,canonicalResponse:response,requests,errors,targetMs:2000,withinTarget:useful.at<=2000,
    samples:1,isP95:false,cache:'browser disabled; server/OS cache state separately recorded',
    provenance:'Synthetic SQL performance fixture; not native, authority, realtime or provider proof.'};
}
