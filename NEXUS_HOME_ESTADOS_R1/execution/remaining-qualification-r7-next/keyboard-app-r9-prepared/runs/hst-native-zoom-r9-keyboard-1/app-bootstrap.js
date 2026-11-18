// PREPARED ONLY: real Tab/Shift+Tab/Enter/Escape; no mouse activation or decisions.
async page=>{
  const cfg={"window": "ROOT_I01_KEYBOARD_APP_OPEN", "phase": "bootstrap", "url": "http://127.0.0.1:56965", "nativeDpr100": 1},checks=[],records=[];
  if(cfg.window!=='ROOT_I01_KEYBOARD_APP_OPEN'||new URL(cfg.url).hostname!=='127.0.0.1')throw Error('Own I01 gate required');
  const check=(id,pass,actual)=>{checks.push({id,pass:!!pass,actual});if(!pass)throw Error(id);};
  const modal=page.locator('dialog[open]');
  const pathOf=e=>{const parts=[];for(let n=e;n&&n!==document.body;n=n.parentElement){const siblings=Array.from(n.parentElement?.children??[]);parts.unshift(n.tagName+':'+siblings.indexOf(n));}return parts.join('/');};
  const focused=async()=>page.locator(':focus').evaluate((e,fn)=>{
    const path=Function('return ('+fn+')')()(e),s=getComputedStyle(e),r=e.getBoundingClientRect();
    return {path,tag:e.tagName,type:e.getAttribute('type'),focusVisible:e.matches(':focus-visible'),paintedFocus:(s.outlineStyle!=='none'&&parseFloat(s.outlineWidth)>0)||s.boxShadow!=='none',outline:s.outlineStyle,outlineWidth:s.outlineWidth,shadow:s.boxShadow,visible:r.width>0&&r.height>0,inModal:!!e.closest('dialog[open]'),homeId:e.closest('[data-home-harness],[data-home-signal]')?.getAttribute('data-home-harness')||e.closest('[data-home-signal]')?.getAttribute('data-home-signal')};
  },String(pathOf));
  const nameProof=async locator=>{
    const ax=await locator.ariaSnapshot(),first=ax.split('\n')[0];
    // A quoted nonempty accessible name is observed from the browser AX snapshot.
    const summary=await locator.evaluate(e=>e.tagName==='SUMMARY');
    const named=/^- [\w-]+ "[^"\n]+"/.test(first)||(summary&&/^- (text|generic): \S/.test(first));
    return {ax:first,named,summaryContentName:summary};
  };
  const tabTo=async(target,label)=>{
    for(let i=0;i<180;i++){
      await page.keyboard.press('Tab');
      if(await target.evaluate(e=>e===document.activeElement)){
        const f=await focused(),n=await nameProof(target);records.push({phase:label,focus:f,name:n});
        check(label+'-named-visible-keyboard-focus',n.named&&f.visible&&f.focusVisible&&f.paintedFocus,{focus:f,name:n});
        return;
      }
    }
    throw Error('Bounded real Tab could not reach '+label);
  };
  const sequential='button,a[href],input:not([type=hidden]),select,textarea,summary,[tabindex]';
  const inventoryOf=async scope=>scope.locator(sequential).evaluateAll((nodes,fn)=>{const path=Function('return ('+fn+')')();return nodes.filter(e=>e.tabIndex>=0&&!e.disabled&&e.getBoundingClientRect().width>0&&e.getBoundingClientRect().height>0&&getComputedStyle(e).visibility!=='hidden'&&!e.closest('[inert]')).map(e=>path(e));},String(pathOf));
  const modalCycle=async label=>{
    check(label+'-ua-modal',await modal.evaluate(e=>e.matches(':modal')),true);
    const inventory=await inventoryOf(modal);check(label+'-modal-controls-nonempty',inventory.length>0,inventory.length);
    const visited=[],cycle=[];
    for(let i=0;i<90&&!inventory.every(p=>visited.includes(p));i++){
      await page.keyboard.press('Tab');
      check(label+'-focused-element-present-'+i,await page.locator(':focus').count()===1,true);
      const f=await focused(),n=await nameProof(page.locator(':focus'));
      check(label+'-contained-'+i,f.inModal&&f.visible&&f.focusVisible&&f.paintedFocus&&n.named,{focus:f,name:n});
      if(visited.includes(f.path)&&!inventory.every(p=>visited.includes(p)))break;
      visited.push(f.path);cycle.push({focus:f,name:n});
    }
    check(label+'-all-enabled-modal-controls-covered',inventory.every(p=>visited.includes(p)),{inventory,visited,missing:inventory.filter(p=>!visited.includes(p)),cycle});
    // Cross both ends with benign keys only; never activate Copy/submit/decision.
    for(const key of ['Tab','Shift+Tab']){
      await page.keyboard.press(key);const f=await focused();
      check(label+'-boundary-contained-'+key,f.inModal&&f.visible&&f.focusVisible&&f.paintedFocus,f);
    }
  };
  const escape=async(id,label)=>{
    await page.keyboard.press('Escape');await modal.waitFor({state:'hidden'});
    const deadline=Date.now()+2500;let f;
    do{f=await focused();if(f.homeId===id)break;await page.waitForTimeout(50);}while(Date.now()<deadline);
    check(label+'-escape-restores-exact-origin',f.homeId===id,f);
  };
  try{
    if(cfg.phase==='bootstrap'){
      page.__i01Writes=[];page.__i01Errors=[];
      page.on('request',r=>{if(!['GET','HEAD','OPTIONS'].includes(r.method()))page.__i01Writes.push({method:r.method(),path:new URL(r.url()).pathname});});
      page.on('pageerror',e=>page.__i01Errors.push(e.message));
      await page.addInitScript(origin=>{if(location.origin!==origin)return;localStorage.setItem('okto-nexus-home-operational','enabled');localStorage.setItem('okto-nexus-workspace','all');localStorage.setItem('okto-nexus:metrics-opt-in-prompt-dismissed:1.0.0',new Date().toISOString());},new URL(cfg.url).origin);
      await page.setViewportSize({width:1440,height:1000});await page.goto(cfg.url);await page.getByTestId('home-follow-up').waitFor({timeout:25000});
      const g=await page.evaluate(()=>({innerWidth,devicePixelRatio,scale:visualViewport?.scale}));
      check('native100-desktop',g.innerWidth===1440&&Math.abs(g.devicePixelRatio-cfg.nativeDpr100)<.03&&g.scale===1,g);
    }else if(cfg.phase==='case'){
      check('original-question-valid-before',Date.now()<Date.parse(cfg.expiresAt),{expiresAt:cfg.expiresAt});
      await page.reload();await page.getByTestId('home-follow-up').waitFor({timeout:25000});
      const harness=id=>page.locator('[data-home-harness='+JSON.stringify(id)+']');
      const signal=id=>page.locator('[data-home-signal='+JSON.stringify(id)+']');
      const active=harness(cfg.bCard).getByRole('button',{name:'Follow activity',exact:true});
      const request=signal(cfg.requestCard).getByRole('button',{name:'Respond',exact:true});
      const result=signal(cfg.deliveryId).getByRole('button',{name:'View result',exact:true});
      await active.waitFor();await request.waitFor();await result.waitFor();
      check('all-three-populated',await page.locator('[data-home-column]').count()===3&&await page.locator('[data-home-column=active] [data-home-harness]').count()>0&&await page.locator('[data-home-column=needs_you] [data-home-signal]').count()>0&&await page.locator('[data-home-column=results] [data-home-signal]').count()>0,true);
      const inventory=await inventoryOf(page);
      check('tabbable-inventory-nonempty',inventory.length>0,inventory.length);
      const visited=[];let boundary=null;
      for(let i=0;i<220&&!inventory.every(p=>visited.includes(p));i++){
        await page.keyboard.press('Tab');
        if(await page.locator(':focus').count()!==1){boundary='No focused page element before coverage';break;}
        const f=await focused(),n=await nameProof(page.locator(':focus'));
        check('home-control-named-focus-'+i,n.named&&f.visible&&f.focusVisible&&f.paintedFocus,{focus:f,name:n});
        if(visited.includes(f.path)){boundary='Focus repeated before inventory coverage';break;}
        visited.push(f.path);records.push({phase:'home-inventory',focus:f,name:n});
      }
      check('full-home-keyboard-covers-all-actionable',inventory.every(p=>visited.includes(p)),{inventory,visited,missing:inventory.filter(p=>!visited.includes(p)),boundary});
      // Exact retained-session GET is observed before the single Enter activation.
      const read=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/runtime-management/runtime/sessions/'+cfg.bScope.session_id&&r.request().method()==='GET',{timeout:15000}).then(response=>({response})).catch(error=>({error:String(error)}));
      await tabTo(active,'active');await page.keyboard.press('Enter');await modal.waitFor();
      const observed=await read;check('active-exact-metadata-arrived',!!observed.response,observed.error??true);
      const raw=await observed.response.json(),body=raw.data??raw;
      check('active-full-canonical-scope',observed.response.status()===200&&Object.keys(cfg.bScope).every(k=>body.scope?.[k]===cfg.bScope[k]),{status:observed.response.status(),scope:body.scope});
      await modal.getByText(cfg.bMarker,{exact:false}).first().waitFor();await modalCycle('active');await escape(cfg.bCard,'active');
      await tabTo(request,'needs-you');await page.keyboard.press('Enter');await modal.waitFor();
      const decision=modal.getByRole('region',{name:'Native runtime decision',exact:true});await decision.waitFor();
      await decision.getByText('Session '+cfg.a2Scope.session_id,{exact:false}).waitFor();
      const input=decision.getByRole('listbox',{name:'Choose fixture output format',exact:true});await input.waitFor();
      check('request-original-unanswered',await input.evaluate(e=>e.selectedOptions.length===0),{requestId:cfg.requestId,session:cfg.a2Scope.session_id});
      const deny=decision.getByRole('button',{name:'Deny runtime request',exact:true});await deny.waitFor();
      const readyDeadline=Math.min(Date.now()+12000,Date.parse(cfg.expiresAt));
      while(!await deny.isEnabled()&&Date.now()<readyDeadline)await page.waitForTimeout(50);
      check('canonical-request-controls-ready-before-inventory',await deny.isEnabled(),{session:cfg.a2Scope.session_id});
      await modalCycle('needs-you');check('tab-does-not-select-answer',await input.evaluate(e=>e.selectedOptions.length===0),true);await escape(cfg.requestCard,'needs-you');
      await tabTo(result,'results');await page.keyboard.press('Enter');await modal.waitFor();
      const target=JSON.parse(new URL(page.url()).searchParams.get('home_target')||'null');
      check('result-exact-target',!!target&&Object.keys(cfg.deliveryTarget).every(k=>target[k]===cfg.deliveryTarget[k]),target);
      await modalCycle('results');await escape(cfg.deliveryId,'results');
      check('original-question-valid-after',Date.now()<Date.parse(cfg.expiresAt),{expiresAt:cfg.expiresAt});
      await page.screenshot({path:cfg.outputPrefix+'-desktop.png'});
    }else throw Error('Unknown I01 phase');
    check('zero-browser-writes',page.__i01Writes.length===0,page.__i01Writes);check('zero-page-errors',page.__i01Errors.length===0,page.__i01Errors);
    return {status:'PASS_I01_EXECUTED_SUBSET',phase:cfg.phase,checks,records,limits:['Desktop native100 only; no AT speech/theme claim','Tab inventory covers visible enabled sequential controls; collapsed content remains collapsed','No Enter on submit/decision; no answer selection or native execution control']};
  }catch(error){return {status:'INCOMPLETE_I01',phase:cfg.phase,checks,records,error:String(error),writes:page.__i01Writes??[],pageErrors:page.__i01Errors??[],homeAX:await page.getByTestId('home-follow-up').ariaSnapshot().catch(()=>null),modalAX:await modal.ariaSnapshot().catch(()=>null)};}
}
