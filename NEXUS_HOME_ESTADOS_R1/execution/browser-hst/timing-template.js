// CLI run-code function factory: replace __CONFIG__ with public own-fixture data.
async (page) => {
  const cfg = __CONFIG__;
  const network = [];
  await page.setViewportSize({width:1440,height:1100});
  // Load PRIVATE Temp storage with the CLI storage-state command beforehand.
  // Cookie values never enter this script, a public result, or a tool argument.
  const cdp = await page.context().newCDPSession(page);
  await cdp.send('Network.enable');
  await cdp.send('Network.setCacheDisabled',{cacheDisabled:true});
  await page.addInitScript(({workspace})=>{
    localStorage.setItem('okto-nexus-home-operational','enabled');
    localStorage.setItem('okto-nexus-workspace',workspace);
    window.__hstUseful=null;
    const observer=new MutationObserver(()=>{
      if(window.__hstUseful!==null)return;
      const board=document.querySelector('[data-testid="home-board"]');
      const cards=board?.querySelectorAll('[data-home-harness]');
      const columns=board?.querySelectorAll('[data-home-column]');
      if(!cards?.length || columns?.length!==3)return;
      if(!document.querySelector('[data-home-badge="Idle"]')||
         ![...document.querySelectorAll('button')].some(b=>b.textContent?.trim()==='Ask for work or chat'))return;
      // Appearance is measured here; healthy canonical data is validated below.
      window.__hstUseful={at:performance.now(),timeOrigin:performance.timeOrigin,
        cardIds:[...cards].map(e=>e.getAttribute('data-home-harness')),
        text:board.innerText};
    });
    observer.observe(document,{subtree:true,childList:true,characterData:true});
  },{workspace:cfg.workspace_id});
  page.on('request',r=>{
    if(new URL(r.url()).pathname==='/api/v1/home/harness-board')
      network.push({kind:'request',at:Date.now(),url:new URL(r.url()).pathname});
  });
  page.on('response',async r=>{
    if(new URL(r.url()).pathname!=='/api/v1/home/harness-board')return;
    const body=await r.json();
    network.push({kind:'response',at:Date.now(),status:r.status(),body});
  });
  const anchor={hostWallMs:Date.now(),navigation:'page.goto',cacheDisabled:true};
  await page.goto(cfg.url,{waitUntil:'domcontentloaded'});
  await page.waitForFunction(()=>window.__hstUseful!==null,{timeout:30000});
  await page.waitForTimeout(300); // let response metadata settle, not part of DOM timing
  const useful=await page.evaluate(()=>window.__hstUseful);
  const responses=network.filter(r=>r.kind==='response'&&r.status===200);
  const latest=responses.at(-1)?.body;
  const board=latest?.data??latest;
  if(!board || board.presentation_version!==2 || board.server_id!==cfg.server_id)
    throw Error('Healthy canonical v2/server proof absent; DOM timing unqualified');
  const sources=board.source_status;
  if(!['ready','partial'].includes(board.status)||!sources||!Object.entries(sources).every(([key,v])=>v==='ready'||key==='external'&&v==='disabled'))
    throw Error('Partial/error data cannot qualify healthy first-useful timing');
  const canonicalIds=Object.values(board.columns).flatMap(c=>c.items).filter(i=>i.kind==='harness').map(i=>i.id).sort();
  if(JSON.stringify([...useful.cardIds].sort())!==JSON.stringify(canonicalIds))
    throw Error('First-useful DOM did not match canonical v2 harness IDs');
  await page.screenshot({path:cfg.screenshot,fullPage:false});
  return {status:'SINGLE_LOAD_MEASUREMENT',anchor,useful,network,
    viewport:{width:1440,height:1100},samples:1,isP95:false,
    targetMs:2000,withinTarget:useful.at<=2000,
    caveat:'Own synthetic fixture, one cold-profile load; no production percentile claim.'};
}
