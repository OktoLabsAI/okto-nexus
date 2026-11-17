async page => {
  const cfg={"window": "EXPERIENCE_FUNCTIONAL_WINDOW_OPEN", "phase": "naming", "url": "http://127.0.0.1:56973", "screenshotPrefix": "C:\\Users\\jpamb\\AppData\\Local\\Temp\\nexus-hst-browser-e922fzsc\\experience-mobile"};
  if(cfg.window!=='EXPERIENCE_FUNCTIONAL_WINDOW_OPEN')throw Error('Execution window not granted');
  const checks=[],posts=[],errors=[];
  const check=(id,ok,actual)=>{checks.push({id,pass:!!ok,actual});if(!ok)throw Error(id);};
  page.on('request',r=>{if(r.method()==='POST')posts.push({path:new URL(r.url()).pathname});});
  page.on('pageerror',e=>errors.push(e.message));
  const modal=page.locator('dialog[open]');
  const harness=id=>page.locator('[data-home-harness='+JSON.stringify(id)+']');
  const close=async()=>{await modal.getByRole('button',{name:'Close',exact:true}).click();await modal.waitFor({state:'hidden'});};
  const open=async id=>{await harness(id).getByRole('button',{name:'Follow activity',exact:true}).click();await modal.waitFor();};
  const key=s=>JSON.stringify([s.scope.server_id,s.scope.executor_id,s.scope.workspace_id,s.scope.session_id]);
  try {
    if(cfg.phase==='naming'){
      await page.addInitScript(()=>{localStorage.setItem('okto-nexus-home-operational','enabled');localStorage.setItem('okto-nexus-workspace','all');localStorage.setItem('okto-nexus:metrics-opt-in-prompt-dismissed:1.0.0',new Date().toISOString());});
      await page.goto(cfg.url);
      await page.locator('[data-testid="home-follow-up"]').waitFor({timeout:25000});
      const button=page.getByTestId('header-menu');await button.waitFor();
      const attributes=await button.evaluate(e=>({ariaLabel:e.getAttribute('aria-label'),title:e.getAttribute('title'),text:e.textContent}));
      const ax=await button.ariaSnapshot();
      const name=/button\s+"([^"\n]+)"/.exec(ax)?.[1]||'';
      check('I01-header-menu-accessible-name',name.trim().length>0,{attributes,ariaSnapshot:ax,computedNameFromAX:name});
      return {status:'PASS_NAMING_PREFLIGHT',checks,posts,errors};
    }
    if(cfg.phase==='base'){
      await open(cfg.bCard);
      const select=modal.getByLabel('Choose a session',{exact:true});
      await select.waitFor();
      await page.waitForFunction(({k})=>document.querySelector('dialog[open] select')?.value===k,{k:key(cfg.b1)});
      check('G01-unique-complete-session-selected',await select.inputValue()===key(cfg.b1),{session:cfg.b1.scope.session_id});
      await modal.getByText(cfg.b1.marker,{exact:false}).first().waitFor({timeout:12000});
      check('G01-one-modal-one-gesture-exact-output',await modal.count()===1,true);await close();
      await open(cfg.aCard);
      await modal.getByText('No session is currently available.',{exact:false}).waitFor();
      check('G04-registered-no-session-no-implicit-open',await modal.locator('select').count()===0,{policy:cfg.policies});
      await close();
    } else if(cfg.phase==='history'){
      // Only replace the preview query parameter; route.fetch uses the actual canonical API.
      let limited=null;
      const pattern='**/api/v1/home/harness-board?*';
      await page.route(pattern,async route=>{const u=new URL(route.request().url());u.searchParams.set('preview','1');const response=await route.fetch({url:u.href});const bytes=await response.body();const body=JSON.parse(bytes.toString());limited={url:u.pathname+u.search,body};await route.fulfill({response,body:bytes});});
      try {
        await page.getByRole('button',{name:'Refresh',exact:true}).click();
        await page.waitForTimeout(800);
        check('G02-canonical-preview-query-observed',!!limited,limited?.url);
        const items=Object.values(limited.body.columns).flatMap(c=>c.items);
        const b=items.find(c=>c.id===cfg.bCard);
        check('G02-one-preview-not-unique',b?.sessions?.length===1&&b.sessions_total===2&&b.has_more_sessions===true,{preview:b?.sessions?.length,total:b?.sessions_total,hasMore:b?.has_more_sessions});
        await open(cfg.bCard);const select=modal.getByLabel('Choose a session',{exact:true});await select.waitFor();
        check('G02-no-automatic-preview-choice',await select.inputValue()==='',await select.inputValue());
        const labels=[];
        for(const session of cfg.sessions){
          const value=key(session);
          // IDs are values, not an assumption about visible title.
          const label=await select.locator('option').evaluateAll((options,v)=>options.find(o=>o.value===v)?.textContent??null,value);
          check('G03-known-session-option-'+session.scope.session_id,!!label&&label.includes(session.lifecycle_state)&&label.includes(cfg.projectLabel),label);
          await select.selectOption(value);await modal.getByText(session.marker,{exact:false}).first().waitFor({timeout:12000});labels.push(label);
        }
        check('G03-distinct-session-targets',new Set(cfg.sessions.map(s=>s.scope.session_id)).size===2,labels);
        await close();
      } finally {await page.unroute(pattern);}
    } else if(cfg.phase==='external'){
      await page.getByRole('button',{name:'Refresh',exact:true}).click();
      await page.getByText(/partial|unavailable/i).first().waitFor({timeout:15000});
      await open(cfg.bCard);const select=modal.getByLabel('Choose a session',{exact:true});await select.waitFor();await select.selectOption(key(cfg.b2));
      await modal.getByText(cfg.b2.marker,{exact:false}).first().waitFor({timeout:12000});
      check('F10-native-exact-read-survives-external-source-failure',true,{scope:cfg.b2.scope});await close();
    } else if(cfg.phase==='themes-mobile'){
      const semantics=[];
      for(let i=0;i<2;i++){
        await page.getByTestId('header-menu').click();await page.getByTestId('theme-toggle').click();
        const labels=await page.locator('[data-home-badge]').allTextContents();
        semantics.push({dark:await page.locator('html').evaluate(e=>e.classList.contains('dark')),labels});
        check('I04-semantic-labels-theme-'+i,labels.length>0&&labels.some(x=>/Idle|Working|Unknown|last known|waiting|pending/i.test(x)),labels);
      }
      check('I04-both-themes-same-meaning',semantics[0].dark!==semantics[1].dark&&JSON.stringify(semantics[0].labels)===JSON.stringify(semantics[1].labels),semantics);
      await page.setViewportSize({width:360,height:900});
      const nav=page.getByTestId('mobile-nav-close');if(await nav.isVisible().catch(()=>false))await nav.click();
      const columns=page.locator('[data-home-column]');const boxes=await columns.evaluateAll(nodes=>nodes.map(e=>{const r=e.getBoundingClientRect();return {column:e.getAttribute('data-home-column'),x:r.x,y:r.y,width:r.width,height:r.height};}));
      check('I05-360-stack-no-horizontal-overflow',boxes.length===3&&boxes.every((b,i)=>b.width<=360&&(!i||b.y>boxes[i-1].y))&&await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),boxes);
      for(const name of ['active','needs_you','results']){await page.locator('[data-home-column='+name+']').scrollIntoViewIfNeeded();await page.screenshot({path:cfg.screenshotPrefix+'-'+name+'.png'});}
      await page.setViewportSize({width:1440,height:1100});
    } else if(cfg.phase==='active'){
      await page.getByRole('button',{name:'Refresh',exact:true}).click();
      for(const column of ['active','needs_you','results'])await page.locator('[data-home-column='+column+']').locator('[data-home-harness],[data-home-signal]').first().waitFor({timeout:15000});
      const labels=await page.locator('[data-home-harness],[data-home-signal]').allTextContents();
      check('G05-authorized-projects-readable',labels.some(t=>t.includes(cfg.projectA))&&labels.some(t=>t.includes(cfg.projectB)),labels);
      const a=harness(cfg.aCard);await a.getByText('Working',{exact:true}).waitFor();
      check('G06-no-invented-state-duration',cfg.stateSince===null?await a.getByText('State since',{exact:false}).count()===0:true,{stateSince:cfg.stateSince});
      // Inventory includes shell controls; do not remove unnamed elements from the oracle.
      const inventory=await page.locator('button:visible,a[href]:visible,input:visible,select:visible,textarea:visible').evaluateAll(nodes=>nodes.map(e=>({tag:e.tagName,disabled:e.disabled===true,label:e.getAttribute('aria-label'),title:e.getAttribute('title'),text:e.textContent,labels:e.labels?Array.from(e.labels).map(l=>l.textContent):[]})));
      const ax=await page.locator('body').ariaSnapshot();
      const visits=[];for(let i=0;i<Math.min(inventory.length+3,100);i++){await page.keyboard.press('Tab');visits.push(await page.evaluate(()=>{const e=document.activeElement;return {tag:e?.tagName,tid:e?.getAttribute('data-testid'),harness:e?.closest('[data-home-harness]')?.getAttribute('data-home-harness'),text:e?.textContent};}));}
      await page.keyboard.press('Shift+Tab');
      check('I01-tab-reaches-populated-board',visits.some(v=>v.harness===cfg.aCard),{inventory,ariaSnapshot:ax,visits});
      await open(cfg.aCard);const select=modal.getByLabel('Choose a session',{exact:true});await select.waitFor();await select.selectOption(key(cfg.a2));
      await modal.getByRole('region',{name:'Pending actions'}).getByRole('button',{name:'Respond',exact:true}).first().click();
      await modal.locator('input[type=radio]').first().waitFor();
      await page.evaluate(()=>{window.__expModal=document.querySelector('dialog[open]');});
      check('F02-panel-initial-exact-question',await modal.count()===1,{session:cfg.a2.scope.session_id});
    } else if(cfg.phase==='panel-after'){
      const response=await page.waitForResponse(async r=>{if(!new URL(r.url()).pathname.endsWith('/home/harness-board')||r.status()!==200)return false;try{return (await r.json()).revision===cfg.expectedRevision;}catch{return false;}},{timeout:35000});
      check('F02-authoritative-poll-with-unrelated-change',response.status()===200,{revision:cfg.expectedRevision});
      const same=await page.evaluate(()=>window.__expModal===document.querySelector('dialog[open]'));
      check('F02-unrelated-change-retains-panel',same&&await modal.locator('input[type=radio]').count()>0,true);
      check('F13-update-notice-not-alert',(await modal.getByRole('alert').allTextContents()).length===0,await modal.getByRole('status').allTextContents());
    } else if(cfg.phase==='moved-close'){
      const response=await page.waitForResponse(async r=>{if(!new URL(r.url()).pathname.endsWith('/home/harness-board')||r.status()!==200)return false;try{return (await r.json()).revision===cfg.expectedRevision;}catch{return false;}},{timeout:35000});
      check('F07-authoritative-poll-harness-moved',response.status()===200,{revision:cfg.expectedRevision});
      check('F07-terminal-change-retains-exact-panel',await page.evaluate(()=>window.__expModal===document.querySelector('dialog[open]')),true);
      await page.keyboard.press('Escape');await modal.waitFor({state:'hidden'});await page.waitForTimeout(300);
      const focus=await page.evaluate(()=>({id:document.activeElement?.closest('[data-home-harness]')?.getAttribute('data-home-harness'),text:document.activeElement?.textContent,tag:document.activeElement?.tagName}));
      check('I02-focus-same-harness-or-heading',focus.id===cfg.aCard||(focus.tag==='H1'&&focus.text==='Home'),focus);
      check('F07-canonical-moved-harness-not-neighbor',await page.locator('[data-home-column=needs_you]').locator('[data-home-harness='+JSON.stringify(cfg.aCard)+']').count()===1,true);
    } else throw Error('Unknown phase');
    check('zero-browser-POST',posts.length===0,posts);check('zero-page-errors',errors.length===0,errors);
    return {status:'PASS_EXECUTED_SUBSET',phase:cfg.phase,checks,posts,errors,unasserted:['specific meaningful session titles without a canonical producer','native 200 percent zoom','screen reader speech','full keyboard coverage beyond enumerated traversal','F12 new decision (prior evidence only)']};
  }catch(error){return {status:checks.some(c=>c.id==='I01-header-menu-accessible-name'&&!c.pass)?'PRODUCT_DEFECT_UNNAMED_HEADER_MENU':'INCOMPLETE',phase:cfg.phase,checks,posts,errors,error:String(error)};}
}
