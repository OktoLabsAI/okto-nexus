// PREPARED ONLY. Themes by actual UI; meaning by text and AX, never color alone.
async page=>{
  const cfg=__CONFIG__,checks=[],observations=[];
  if(cfg.window!=='ROOT_I04_THEME_APP_OPEN'||new URL(cfg.url).hostname!=='127.0.0.1')throw Error('Own theme gate required');
  const check=(id,pass,actual)=>{checks.push({id,pass:!!pass,actual});if(!pass)throw Error(id);};
  const harness=id=>page.locator('[data-home-harness='+JSON.stringify(id)+']');
  const signal=id=>page.locator('[data-home-signal='+JSON.stringify(id)+']');
  const setTheme=async theme=>{
    const dark=await page.locator('html').evaluate(e=>e.classList.contains('dark'));
    if(dark!==(theme==='dark')){
      await page.getByRole('button',{name:'Application menu',exact:true}).click();
      await page.getByRole('button',{name:theme==='dark'?'Dark Mode':'Light Mode',exact:true}).click();
    }
    await page.waitForFunction(dark=>document.documentElement.classList.contains('dark')===dark,theme==='dark');
    check('actual-UI-theme-'+cfg.phase+'-'+theme,await page.locator('html').evaluate((e,expected)=>e.classList.contains('dark')===expected,theme==='dark'),theme);
  };
  const textProof=async(locator,label)=>{
    await locator.waitFor();const text=await locator.innerText(),ax=await locator.ariaSnapshot();
    check(cfg.phase+'-'+label+'-noncolor-meaning',text.trim().length>0&&ax.includes(text.trim()),{text,ax,svgCount:await locator.locator('svg').count()});
  };
  try{
    if(cfg.phase==='bootstrap'){
      page.__i04Writes=[];page.__i04Errors=[];page.__i04Boards=[];
      page.on('request',r=>{if(!['GET','HEAD','OPTIONS'].includes(r.method()))page.__i04Writes.push({method:r.method(),path:new URL(r.url()).pathname});});
      page.on('pageerror',e=>page.__i04Errors.push(e.message));
      page.on('response',async response=>{
        if(!new URL(response.url()).pathname.endsWith('/home/harness-board')||response.status()!==200)return;
        try{const raw=await response.json(),v=raw.data??raw;page.__i04Boards.push({at:Date.now(),revision:v.revision,presentation_version:v.presentation_version,status:v.status,source_status:v.source_status,columns:Object.fromEntries(Object.entries(v.columns).map(([name,slice])=>[name,slice.items.map(item=>({id:item.id,kind:item.kind,connection:item.connection?.binding_id,status:item.operational_status,requestId:item.request?.source_id,session:item.request?.session_id,semantics:item.delivery_semantics??item.result?.delivery_semantics}))]))});}catch{/* Aborted response is not proof. */}
      });
      await page.addInitScript(origin=>{if(location.origin!==origin)return;localStorage.setItem('okto-nexus-home-operational','enabled');localStorage.setItem('okto-nexus-workspace','all');localStorage.setItem('okto-nexus:metrics-opt-in-prompt-dismissed:1.0.0',new Date().toISOString());},new URL(cfg.url).origin);
      await page.setViewportSize({width:1440,height:1000});await page.goto(cfg.url);await page.getByTestId('home-follow-up').waitFor({timeout:25000});
      const g=await page.evaluate(()=>({innerWidth,devicePixelRatio,scale:visualViewport?.scale}));check('native100',g.innerWidth===1440&&Math.abs(g.devicePixelRatio-cfg.nativeDpr100)<.03&&g.scale===1,g);
    }else if(['known','unknown'].includes(cfg.phase)){
      check('original-question-valid-before-'+cfg.phase,Date.now()<Date.parse(cfg.expiresAt),{expiresAt:cfg.expiresAt});
      const start=Date.now();await page.getByRole('button',{name:'Refresh',exact:true}).click();
      const end=Math.min(Date.now()+15000,Date.parse(cfg.expiresAt));let actual;
      do{
        actual=page.__i04Boards.find(v=>{
          if(v.at<start||v.presentation_version!==2)return false;
          const items=Object.values(v.columns).flat(),a=items.find(i=>i.id===cfg.aCard),b=items.find(i=>i.id===cfg.bCard);
          return cfg.phase==='known'?a?.status?.activity==='working'&&b?.status?.activity==='idle'&&a.status.freshness==='current'&&b.status.freshness==='current':a?.status?.activity==='unknown'&&b?.status?.activity==='unknown'&&a.status.freshness==='unavailable'&&b.status.freshness==='unavailable';
        });
        if(actual)break;await page.waitForTimeout(50);
      }while(Date.now()<end);
      check('canonical-'+cfg.phase+'-HTTP-snapshot',!!actual,actual);
      const apply=page.getByRole('button',{name:'Apply updates',exact:true});if(await apply.isVisible().catch(()=>false))await apply.click();
      const items=Object.values(actual.columns).flat();
      const a=items.find(i=>i.id===cfg.aCard),b=items.find(i=>i.id===cfg.bCard),request=items.find(i=>i.id===cfg.requestCard),failed=items.find(i=>i.id===cfg.failedId);
      check('same-canonical-IDs-'+cfg.phase,!!a&&!!b&&request?.requestId===cfg.requestId&&request?.session===cfg.a2Scope.session_id&&failed?.semantics?.execution_outcome==='failed',{a:a?.id,b:b?.id,request:request?.id,failed:failed?.id,failedSemantics:failed?.semantics});
      check('canonical-operational-'+cfg.phase,cfg.phase==='known'?a.status.activity==='working'&&b.status.activity==='idle'&&a.status.freshness==='current'&&b.status.freshness==='current':a.status.activity==='unknown'&&b.status.activity==='unknown'&&a.status.freshness==='unavailable'&&b.status.freshness==='unavailable',{a:a.status,b:b.status});
      for(const theme of ['light','dark']){
        await setTheme(theme);
        await textProof(harness(cfg.aCard).locator('[data-home-badge='+JSON.stringify(cfg.phase==='known'?'Working':'State unconfirmed')+']'),'a-'+theme);
        await textProof(harness(cfg.bCard).locator('[data-home-badge='+JSON.stringify(cfg.phase==='known'?'Idle':'State unconfirmed')+']'),'b-'+theme);
        await textProof(signal(cfg.requestCard).getByText('Response pending',{exact:true}),'request-'+theme);
        await textProof(signal(cfg.failedId).getByText('Execution ended with failure',{exact:true}),'failed-'+theme);
        const requestButton=signal(cfg.requestCard).getByRole('button',{name:'Respond',exact:true}),failedButton=signal(cfg.failedId).getByRole('button',{name:'View result',exact:true});
        check('named-context-actions-'+cfg.phase+'-'+theme,(await requestButton.ariaSnapshot()).includes('Respond')&&(await failedButton.ariaSnapshot()).includes('View result'),{requestEnabled:await requestButton.isEnabled(),failedEnabled:await failedButton.isEnabled()});
        await page.getByTestId('home-follow-up').scrollIntoViewIfNeeded();await page.screenshot({path:cfg.outputPrefix+'-'+cfg.phase+'-'+theme+'.png'});
        observations.push({phase:cfg.phase,theme,revision:actual.revision,source_status:actual.source_status,cardIds:[a.id,b.id,request.id,failed.id],stateIcons:'Harness badges are text spans in current source; no dedicated state icon is invented. Text and AX carry meaning.'});
      }
      check('original-question-valid-after-'+cfg.phase,Date.now()<Date.parse(cfg.expiresAt),{expiresAt:cfg.expiresAt});
    }else throw Error('Unknown theme phase');
    check('zero-browser-writes',page.__i04Writes.length===0,page.__i04Writes);check('zero-page-errors',page.__i04Errors.length===0,page.__i04Errors);
    return {status:'PASS_I04_EXECUTED_SUBSET',phase:cfg.phase,checks,observations,limits:['Five observed meanings only; not full state matrix','Inert canonical terminal-failed peer; query fault is fixture-only read-source failure','No AT/human/color-contrast measurement claim; no state icons invented']};
  }catch(error){return {status:'INCOMPLETE_I04',phase:cfg.phase,checks,observations,error:String(error),writes:page.__i04Writes??[],pageErrors:page.__i04Errors??[],homeAX:await page.getByTestId('home-follow-up').ariaSnapshot().catch(()=>null)};}
}
