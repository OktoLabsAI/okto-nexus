// Browser-only diagnostic. No application, authority, native provider or synthetic trap.
async page=>{
  const cfg={"window": "ROOT_NATIVE_DIALOG_FOCUS", "probeOrigin": "http://127.0.0.1:65206", "outputPrefix": "C:\\Users\\jpamb\\AppData\\Local\\Temp\\nexus-hst-browser-dbnnmrl4\\native-zoom"},checks=[],records=[];
  if(cfg.window!=='ROOT_NATIVE_DIALOG_FOCUS'||new URL(cfg.probeOrigin).hostname!=='127.0.0.1')throw Error('Own browser-only gate required');
  const check=(id,pass,actual)=>{checks.push({id,pass:!!pass,actual});if(!pass)throw Error(id);};
  const capture=async label=>{
    const state=await page.evaluate(()=>{
      const e=document.activeElement,d=document.querySelector('#diagnostic'),s=e?getComputedStyle(e):null;
      return {hasFocus:document.hasFocus(),focusCount:document.querySelectorAll(':focus').length,activeTag:e?.tagName,activeId:e?.id,activeMatchesFocus:e?.matches(':focus'),focusVisible:e?.matches(':focus-visible'),insideDialog:!!e?.closest('#diagnostic'),modal:d.matches(':modal'),open:d.open,outline:s?.outlineStyle,outlineWidth:s?.outlineWidth,shadow:s?.boxShadow,events:window.probeEvents.splice(0)};
    });
    state.label=label;state.focusLocatorCount=await page.locator(':focus').count();
    state.focusAX=state.focusLocatorCount===1?await page.locator(':focus').ariaSnapshot():null;
    records.push(state);return state;
  };
  try{
    await page.setViewportSize({width:1440,height:1000});await page.goto(cfg.probeOrigin+'/probe');
    await page.getByRole('heading',{name:'Own native dialog focus diagnostic',exact:true}).waitFor();
    const opener=page.getByRole('button',{name:'Open diagnostic dialog',exact:true});
    await capture('before-open');
    let reached=false;for(let i=0;i<6;i++){await page.keyboard.press('Tab');await capture('to-opener-'+i);if(await opener.evaluate(e=>e===document.activeElement)){reached=true;break;}}
    check('opener-keyboard-reached',reached,true);await page.keyboard.press('Enter');
    await page.locator('#diagnostic[open]').waitFor();const initial=await capture('initial-modal-focus');
    check('initial-UA-modal',initial.modal&&initial.open,initial);
    const inventory=await page.locator('#diagnostic button,#diagnostic input,#diagnostic [tabindex]').evaluateAll(nodes=>nodes.filter(e=>e.tabIndex>=0&&!e.disabled).map(e=>e.id));
    check('eleven-synthetic-controls',inventory.length===11,inventory);
    for(const key of ['Tab','Shift+Tab'])for(let i=0;i<16;i++){
      await page.keyboard.press(key);const state=await capture(key+'-'+i);
      check('UA-modal-stays-open-'+key+'-'+i,state.modal&&state.open,true);
      // Native dialogs may permit browser chrome. Only actual focused page content outside the modal is forbidden.
      check('no-focused-outside-page-control-'+key+'-'+i,!(state.hasFocus&&state.focusCount>0&&!state.insideDialog),state);
    }
    const visited=[...new Set(records.filter(s=>s.modal&&s.hasFocus&&s.activeMatchesFocus&&s.insideDialog).map(s=>s.activeId))];
    check('all-controls-including-initial-observed',inventory.every(id=>visited.includes(id)),{inventory,visited});
    // Benign keys return from an outside-document position without programmatic focus.
    for(let i=0;i<8;i++){const s=await capture('before-escape-'+i);if(s.hasFocus&&s.insideDialog)break;await page.keyboard.press('Shift+Tab');}
    await page.keyboard.press('Escape');await page.locator('#diagnostic').waitFor({state:'hidden'});
    const end=await capture('after-escape');check('escape-returns-opener',end.activeId==='open'&&end.hasFocus,end);
    await page.screenshot({path:cfg.outputPrefix+'-closed.png'});
    return {status:'DIAGNOSTIC_COMPLETED_NATIVE_DIALOG',checks,records,observations:{outsideDocument:records.filter(s=>s.modal&&!s.hasFocus),zeroFocusCount:records.filter(s=>s.modal&&s.focusCount===0)},limits:['Static native-dialog probe only; not evidence of the original Nexus failure cause','Outside-document observation does not identify the exact browser chrome widget','No manual trap, CSS focus mutation, programmatic focus or AT']};
  }catch(error){return {status:'INCOMPLETE_NATIVE_DIALOG_DIAGNOSTIC',checks,records,error:String(error),last:await capture('catch').catch(()=>null),pageAX:await page.locator('body').ariaSnapshot().catch(()=>null)};}
}
