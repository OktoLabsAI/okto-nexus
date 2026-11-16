// Real Playwright browser checks over browser_fixture.py; no product mutations.
// Run via playwright-cli run-code --filename. All auth changes below are routed fixtures.
async (page) => {
  page.setDefaultTimeout(7000);
  const origin = new URL(page.url()).origin;
  const checks = [], mutations = [], errors = [], browserDialogs = [];
  const publish = async status => page.evaluate(value => localStorage.setItem('home-r1-final-identity-evidence',JSON.stringify(value)),{status,checks,mutationRequests:mutations,pageErrors:errors,browserDialogs});
  const onDialog = async dialog => {
    browserDialogs.push({type:dialog.type(),message:dialog.message()});
    if(dialog.type()==='beforeunload') await dialog.accept();
    else {await dialog.dismiss();errors.push('Unexpected browser dialog: '+dialog.type());}
  };
  page.on('dialog',onDialog);
  const assert = (ok, message) => { if (!ok) throw new Error(message); };
  const frames = () => page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  const request = r => { if (new URL(r.url()).origin === origin && !['GET','HEAD','OPTIONS'].includes(r.method())) mutations.push({method:r.method(),path:new URL(r.url()).pathname}); };
  const pageError = e => errors.push(e.message);
  page.on('request',request); page.on('pageerror',pageError);
  const routes = [];
  const route = async (pattern, handler) => {routes.push([pattern,handler]);await page.route(pattern,handler);};
  const removeRoutes = async () => {for(const [p,h] of routes.splice(0)) await page.unroute(p,h);};
  const discard = async () => {
    if(await page.getByRole('dialog').count()) {
      await page.keyboard.press('Escape');
      if(await page.getByRole('button',{name:'Discard changes',exact:true}).count()) await page.getByRole('button',{name:'Discard changes',exact:true}).click();
      await page.getByRole('dialog').waitFor({state:'detached'});
    }
  };
  const reset = async () => {
    await removeRoutes(); await discard();
    await page.goto(origin);
    await page.getByRole('heading',{name:'Review the integration',exact:true}).waitFor();
  };
  const run = async (id,action) => {
    try {await reset(); checks.push({id,status:'PASS',detail:await action()});}
    catch(e){checks.push({id,status:'FAIL',error:e.message});}
    await publish('RUNNING');
  };
  const scope = () => page.getByRole('combobox',{name:'Workspace scope'});
  const message = () => page.getByRole('textbox',{name:'Message',exact:true});
  const requestForm = async text => {
    await page.getByRole('button',{name:'New request',exact:true}).click();
    await message().fill(text);
  };
  const tabTo = async (role,name,cap=100) => {
    const target=page.getByRole(role,{name,exact:true});
    for(let i=0;i<cap;i++) {
      if(await target.evaluate(el=>el===document.activeElement)) return i;
      await page.keyboard.press('Tab');
    }
    throw new Error('Keyboard cannot reach '+name);
  };
  try {
    await page.setViewportSize({width:1440,height:1000});
    await run('F06: modal draft prevents implicit workspace/target change; explicit discard allows exact replacement',async()=>{
      await requestForm('Draft A must not follow a different workspace or target.');
      await page.keyboard.press('Escape');
      await page.getByText('Discard unsaved changes?',{exact:true}).waitFor();
      await page.getByRole('button',{name:'Keep editing',exact:true}).click();
      assert(await message().inputValue()==='Draft A must not follow a different workspace or target.','Keep editing lost draft');
      assert(await scope().inputValue()==='home-alpha','Workspace changed without consent');
      const targetBefore=new URL(page.url()).searchParams.get('home_target');
      // The native modal intentionally makes the background inert. Do not force-click it.
      await page.keyboard.press('Escape');
      await page.getByRole('button',{name:'Discard changes',exact:true}).click();
      await page.getByRole('dialog').waitFor({state:'detached'});
      await scope().selectOption('home-beta');
      await page.getByRole('heading',{name:'Lyra: independent request',exact:true}).waitFor();
      await requestForm('Draft B is scoped to Lyra.');
      await page.keyboard.press('Escape');
      await page.getByRole('button',{name:'Discard changes',exact:true}).click();
      await page.getByRole('dialog').waitFor({state:'detached'});
      await page.getByRole('button',{name:'Inspect Lyra: independent request',exact:true}).click();
      await page.getByRole('dialog').getByRole('heading',{name:'browser-handoff-4',exact:true}).waitFor();
      const target=JSON.parse(new URL(page.url()).searchParams.get('home_target'));
      assert(target.workspace_id==='home-beta' && target.handoff_id==='browser-handoff-4','Target switched to wrong scope');
      assert(!(await page.getByRole('dialog').innerText()).includes('Draft A'),'Prior draft copied to target');
      await discard(); await page.getByRole('button',{name:'New request',exact:true}).click();
      assert(await message().inputValue()==='','Discarded draft resurrected');
      await discard();
      return {keepEditingPreserved:true,explicitDiscard:true,scope:'home-beta',exactTarget:target.handoff_id,newComposerEmpty:true,backgroundModalNotBypassed:true,targetBefore};
    });
    await run('A06: retained old-workspace GET cannot overwrite the new workspace or its live form',async()=>{
      let release, captured, finished;
      const capturedPromise=new Promise(r=>captured=r), done=new Promise(r=>finished=r);
      const barrier=new Promise(r=>release=r); let held=false, lateOutcome;
      const handler=async r=>{
        const u=new URL(r.request().url());
        if(held || u.searchParams.get('workspace_id')!=='home-alpha') return r.fallback();
        held=true; const response=await r.fetch(); captured(); await barrier;
        try{await r.fulfill({response});lateOutcome='fulfilled after B form';}
        catch(e){lateOutcome='aborted obsolete request';}
        finally{finished();}
      };
      await route('**/api/v1/home/overview?*',handler);
      try {
        await page.getByRole('button',{name:'Refresh Home',exact:true}).click();
        await capturedPromise;
        await scope().selectOption('home-beta');
        await page.getByRole('heading',{name:'Lyra: independent request',exact:true}).waitFor();
        await requestForm('B-only draft with a stable selection.');
        await message().focus();
        await message().evaluate(e=>{e.dataset.identityProbe='same';e.setSelectionRange(2,8);});
        release();await done;await frames();
        const actual=await message().evaluate(e=>({value:e.value,same:e.dataset.identityProbe==='same',focused:e===document.activeElement,selection:[e.selectionStart,e.selectionEnd]}));
        assert(actual.same&&actual.focused&&actual.selection.join(',')==='2,8','Late A response disturbed B form');
        assert(actual.value==='B-only draft with a stable selection.','Late A response replaced draft');
        assert(await scope().inputValue()==='home-beta','Late A response replaced workspace');
        assert(await page.getByRole('heading',{name:'Review the integration',exact:true}).count()===0,'Late A work leaked into B');
        return {barrierOrdered:true,lateOutcome,scope:'home-beta',form:actual,oldWorkAbsent:true};
      } finally {release();await done;}
    });
    await run('A05: protected list and target stay cleared across back/forward after canonical-shaped 403',async()=>{
      await page.getByRole('button',{name:'Inspect Review the integration',exact:true}).click();
      await page.getByRole('dialog').getByRole('heading',{name:'browser-handoff-0',exact:true}).waitFor();
      await discard();
      await page.getByRole('button',{name:'Inspect Validate the response',exact:true}).click();
      await page.getByRole('dialog').getByRole('heading',{name:'browser-handoff-1',exact:true}).waitFor();
      await route('**/api/v1/home/**',r=>r.fulfill({status:403,contentType:'application/json',body:JSON.stringify({ok:false,error:{code:'PERMISSION_DENIED',message:'Synthetic revoked Home authority'}})}));
      const refused=page.waitForResponse(r=>r.url().includes('/home/overview')&&r.status()===403);
      await page.evaluate(()=>window.dispatchEvent(new Event('focus')));await refused;
      await page.getByText('Operator access is required. Protected Home data has been cleared.',{exact:true}).waitFor();
      const probe=async stage=>{
        await frames();
        assert(await page.getByRole('dialog').count()===0,stage+': protected drawer restored');
        assert(await page.getByRole('heading',{name:'Review the integration',exact:true}).count()===0,stage+': protected list restored');
        assert(await page.getByRole('heading',{name:'Validate the response',exact:true}).count()===0,stage+': protected alternate item restored');
      };
      await probe('403');await page.goBack();await probe('back');await page.goForward();await probe('forward');
      return {revocation:'routed 403, actual Home GET consumer',listCleared:true,drawerCleared:true,backForwardNoProtectedPayload:true,noRealAccountMutation:true};
    });
    await run('A05/F06: synthetic sign-out clears dirty form and browser history cannot revive it',async()=>{
      let loggedOut=false;
      await route('**/api/v1/operator-auth/status',r=>r.fulfill({status:200,contentType:'application/json',body:JSON.stringify({ok:true,data:{authenticated:!loggedOut,configured:true,local:false,username:loggedOut?null:'fixture-operator'}})}));
      await route('**/api/v1/operator-auth/logout',r=>{loggedOut=true;return r.fulfill({status:200,contentType:'application/json',body:JSON.stringify({ok:true,data:{}})});});
      await page.reload();await page.getByRole('button',{name:'Sign out',exact:true}).waitFor();
      await requestForm('Sensitive synthetic draft to remove on logout.');
      await page.keyboard.press('Escape');await page.getByRole('button',{name:'Keep editing',exact:true}).click();
      assert(await message().inputValue()==='Sensitive synthetic draft to remove on logout.','Draft lost before discard');
      await page.keyboard.press('Escape');await page.getByRole('button',{name:'Discard changes',exact:true}).click();
      await page.getByRole('dialog').waitFor({state:'detached'});
      await page.getByRole('button',{name:'Sign out',exact:true}).click();
      await page.getByRole('heading',{name:'Home',exact:true}).waitFor({state:'detached'});
      assert(loggedOut,'Mock logout boundary was not exercised');
      const check=async()=>{
        await frames();
        assert(await page.locator('[data-testid="operational-home"]').count()===0,'Signed-out Home resurrected');
        assert(await page.getByRole('textbox',{name:'Message',exact:true}).count()===0,'Signed-out draft form resurrected');
        assert(!(await page.locator('body').innerText()).includes('Sensitive synthetic draft'),'Draft visible after logout');
      };
      await check();await page.goBack();await check();await page.goForward();await check();
      return {syntheticLogoutRequests:1,backendLogoutRequests:0,historyNoHomeOrDraft:true,realCredentialsUsed:false};
    });
    await run('H01: keyboard reaches filters/cards/drawer/actions and returns focus without pointer assistance',async()=>{
      // Establish keyboard origin through a real Home link reload; subsequent navigation is Tab/keys only.
      await page.reload();await page.getByRole('heading',{name:'Review the integration',exact:true}).waitFor();
      const trace=[];
      trace.push({target:'Workspace scope',tabs:await tabTo('combobox','Workspace scope')});
      trace.push({target:'Filter Home by agent',tabs:await tabTo('combobox','Filter Home by agent')});
      trace.push({target:'Work state',tabs:await tabTo('combobox','Work state')});
      await page.keyboard.press('ArrowDown');await page.keyboard.press('Home');await page.keyboard.press('Enter');
      trace.push({target:'Inspect Review the integration',tabs:await tabTo('button','Inspect Review the integration')});
      await page.keyboard.press('Enter');
      await page.getByRole('dialog').getByRole('heading',{name:'browser-handoff-0',exact:true}).waitFor();
      const focusInDrawer=await page.getByRole('dialog').evaluate(e=>e.contains(document.activeElement));
      assert(focusInDrawer,'Drawer did not receive keyboard focus');
      trace.push({target:'Close modal',tabs:await tabTo('button','Close modal',40)});
      await page.keyboard.press('Escape');await page.getByRole('dialog').waitFor({state:'detached'});
      assert(await page.getByRole('button',{name:'Inspect Review the integration',exact:true}).evaluate(e=>e===document.activeElement),'Focus did not return to card');
      trace.push({target:'New request',tabs:await tabTo('button','New request')});
      await page.keyboard.press('Enter');await page.getByRole('dialog',{name:'New request',exact:true}).waitFor();
      trace.push({target:'Message',tabs:await tabTo('textbox','Message',40)});
      await page.keyboard.type('Keyboard-only unsent draft.');
      trace.push({target:'Handoff',tabs:await tabTo('button','Handoff',40)});await page.keyboard.press('Enter');
      assert(await page.getByRole('button',{name:'Handoff',exact:true}).getAttribute('aria-pressed')==='true','Keyboard mode action failed');
      await page.keyboard.press('Escape');await page.getByText('Discard unsaved changes?',{exact:true}).waitFor();
      trace.push({target:'Discard changes',tabs:await tabTo('button','Discard changes',40)});await page.keyboard.press('Enter');
      await page.getByRole('dialog').waitFor({state:'detached'});
      assert(await page.getByRole('button',{name:'New request',exact:true}).evaluate(e=>e===document.activeElement),'Composer focus did not restore');
      return {keyboardTrace:trace,drawerFocus:true,cardFocusRestored:true,composerFocusRestored:true,submitted:false,limits:'No native approval fixture or real screen-reader speech in this selected keyboard route.'};
    });
    await publish(checks.every(x=>x.status==='PASS')?'PASS':'FAIL');
    return {status:checks.every(x=>x.status==='PASS')?'PASS':'FAIL',checks,mutationRequests:mutations,pageErrors:errors,browserDialogs,
      scope:'Built actual App + own read-only synthetic SQLite/HTTP fixture; routed auth and deterministic delayed GET only. No native harness, provider, credentials or real auth mutation.',
      limitations:['Not a blanket73-scenario or all-control accessibility certification.','Synthetic sign-out POST is fulfilled in browser and never reaches the fixture.']};
  } finally {
    await removeRoutes();await discard();page.off('request',request);page.off('pageerror',pageError);page.off('dialog',onDialog);
  }
}
