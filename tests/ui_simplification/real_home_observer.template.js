async page => {
  const cfg = /* OBSERVER_CONFIG */null;
  if (!cfg) throw Error('Prepare only after approval and observer-ready');
  if (new URL(page.url()).origin !== cfg.origin) throw Error('Wrong Server origin');
  const checks=[], requests=[], blocked=[];
  page.setDefaultTimeout(8000);
  // No headers, request bodies, cookies, passwords, event text or console dumps
  // are returned. Account/login use the human UI in the separate manual phase.
  await page.route('**/*', async route => {
    const req=route.request(); const u=new URL(req.url());
    if(u.origin!==cfg.origin || !['GET','HEAD','OPTIONS'].includes(req.method())) {
      blocked.push({method:req.method(),path:u.pathname}); await route.abort(); return;
    }
    requests.push({method:req.method(),path:u.pathname}); await route.continue();
  });
  const get=async path=>{
    const r=await page.request.get(cfg.origin+path);
    if(r.status()!==200)throw Error('Canonical read unavailable: '+path.split('?')[0]);
    const v=await r.json();return v.data??v;
  };
  const auth=await get('/api/v1/operator-auth/status');
  if(!auth.authenticated||!auth.username||auth.local)throw Error('Require own human cookie session, not loopback bypass');
  const home=page.getByTestId('navigation-sidebar').getByRole('button',{name:'Home',exact:true});
  await home.click();
  const opt=page.getByRole('button',{name:'Use operational Home',exact:true});
  if(await opt.count())await opt.click();
  await page.getByTestId('home-follow-up').waitFor();
  // Workspace selection is via the visible header control in the manual phase;
  // verify its real scope here. No localStorage inventory or synthetic DTO.
  const all=page.getByRole('group',{name:'Follow-up filter',exact:true}).getByRole('button',{name:'All',exact:true});
  await all.click();
  const query='?workspace_id='+encodeURIComponent(cfg.workspace_id)+'&quick=all';
  const overview=await get('/api/v1/home/entries'+query);
  const entries=(overview.items??[]).flatMap(g=>g.children??[]);
  checks.push({name:'Canonical Home page read',status:'PASS',groups:(overview.items??[]).length,
    has_more:overview.has_more,total_is_exact:overview.total_is_exact});
  for(const client of ['codex','claude']) {
    const session=cfg.sessions[client];
    const refs=entries.flatMap(e=>[...(e.sessions??[]),...(e.target?.kind==='session'?[e.target]:[])]);
    const ref=refs.find(r=>r.session_id===session&&r.server_id===cfg.server_id&&r.workspace_id===cfg.workspace_id);
    if(!ref)throw Error('Exact session not in current page; inspect canonical pagination explicitly, never substitute latest: '+client);
    const target={kind:'session',server_id:ref.server_id,executor_id:ref.executor_id,
      workspace_id:ref.workspace_id,session_id:ref.session_id};
    const url=cfg.origin+'/?home_target='+encodeURIComponent(JSON.stringify(target));
    await page.goto(url);
    const dialog=page.getByTestId('home-detail'); await dialog.waitFor();
    const viewer=dialog.getByRole('region',{name:'Session execution output',exact:true});
    await viewer.getByText(session,{exact:true}).waitFor();
    await viewer.getByText('Following live events',{exact:true}).waitFor();
    const one=await page.getByRole('dialog').count()===1&&await viewer.count()===1;
    if(!one)throw Error('Expected one panel and one exact viewer');
    checks.push({name:client+' exact passive session',status:'PASS',target,dialogs:1,viewers:1});
    await dialog.getByRole('button',{name:'Close modal',exact:true}).click();
  }
  if(blocked.length)throw Error('Blocked non-read request; do not mark observation complete');
  return {campaign_id:cfg.campaign_id,status:'PASS_PASSIVE_SUBSCOPE',checks,requests,
    productive_actions:0,marker_written:false,
    limits:['Initial overview page only; missing references fail closed',
      'No transcript or fresh-arrival claim; results require separate visible review',
      'No credentials/cookies or request bodies retained']};
}
