async page=>{
 const cfg={"url": "http://127.0.0.1:59142", "out": "D:/Projetos/Techridy/okto_labs_okto_nexus/output/playwright/r3-harness-board", "bundle": "index-Bljabqt3.js"},checks=[],requests=[],responses=[],pageErrors=[],consoleErrors=[];
 page.setDefaultTimeout(15000);
 const check=(name,ok,data={})=>{checks.push({name,status:ok?'PASS':'FAIL',...data});if(!ok)throw Error(name);};
 const column=n=>page.locator('[data-home-column="'+n+'"]'),card=id=>page.locator('[data-home-harness='+JSON.stringify(id)+']');
 page.on('request',r=>requests.push({method:r.method(),url:r.url()}));page.on('response',r=>responses.push({status:r.status(),url:r.url()}));page.on('pageerror',e=>pageErrors.push(e.message));page.on('console',m=>{if(m.type()==='error')consoleErrors.push(m.text());});
 let board=null;
 try{
  await page.addInitScript(()=>{if(location.protocol==='http:'){localStorage.setItem('okto-nexus-home-operational','enabled');localStorage.setItem('okto-nexus-workspace','ws');localStorage.setItem('okto.nexus.onboarding.completed.v1','true');localStorage.setItem('okto-nexus:metrics-opt-in-prompt-dismissed:1.0.0','test');}});
  await page.setViewportSize({width:1440,height:1100});const received=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/home/harness-board'&&r.status()===200);await page.goto(cfg.url);board=(await(await received).json()).data;
  const all=Object.values(board.columns).flatMap(c=>c.items),harnesses=all.filter(i=>i.kind==='harness'),a=harnesses.find(c=>c.connection.binding_id==='binding'),b=harnesses.find(c=>c.connection.binding_id==='ui-binding-2');
  await page.waitForFunction(()=>document.querySelectorAll('[data-home-harness]').length===2);
  check('Phase1 exact registry produces only two harness cards with the native blocking request on its own harness',board.status==='ready'&&board.inventory.registered_harnesses.value===2&&harnesses.length===2&&a.blocks_harness===true&&a.activity_state==='waiting_for_user'&&board.columns.needs_you.items.some(i=>i.id===a.id)&&board.columns.active.items.some(i=>i.id===b.id)&&a.blocking_requests.some(r=>r.request.kind==='native_question_pending'&&r.request.allowed_actions.includes('respond_native')),{identities:harnesses.map(c=>({id:c.id,connection:c.connection,activity_state:c.activity_state,blocks_harness:c.blocks_harness})),blocking:a.blocking_requests});
  const domIds=await page.locator('[data-home-harness]').evaluateAll(ns=>ns.map(n=>n.dataset.homeHarness));
  check('Harness primary IDs match backend and event previews stay inside their proven parent',JSON.stringify([...domIds].sort())===JSON.stringify(harnesses.map(c=>c.id).sort())&&(await card(a.id).locator('[data-home-event]').count())===a.events_preview.length&&(await card(b.id).locator('[data-home-event]').count())===b.events_preview.length,{domIds});
  const delivery=board.columns.results.items.find(i=>i.kind==='delivery'&&i.result);
  check('Completed delivery is a distinct Results signal with canonical result and proven harness reference',!!delivery&&delivery.completion_evidence==='canonical'&&delivery.harness_refs.some(r=>r.connection.binding_id==='ui-binding-2')&&await page.locator('[data-home-signal='+JSON.stringify(delivery.id)+']').getByRole('button',{name:'View delivery',exact:true}).count()===1,{delivery});
  const follow=page.getByTestId('home-follow-up');
  check('Basic Home has no technical filter fields or duplicated generic observation chooser',await follow.locator('input,select').count()===0&&await page.getByText('Filter details',{exact:true}).count()===0&&await page.getByRole('button',{name:'Connect or resume',exact:true}).count()===0&&await page.getByTestId('home-project-card').getByRole('button',{name:'Add harness',exact:true}).count()===1);
  const handoff=board.columns.needs_you.items.find(i=>i.kind==='request'&&i.request.source_id==='r3-operator-handoff'&&i.request.kind==='verification_pending');
  if(handoff&&handoff.request.category==='action_required'&&handoff.request.allowed_actions.includes('verify_handoff')){
   const read=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/handoffs'&&new URL(r.url()).searchParams.get('handoff_id')==='r3-operator-handoff'&&r.status()===200);await page.locator('[data-home-signal='+JSON.stringify(handoff.id)+']').getByRole('button',{name:'Review request',exact:true}).click();const detail=await read;
   check('Public operator-directed handoff is canonically actionable and opens its exact handoff GET without impersonation or decision',await page.getByRole('dialog').count()===1&&requests.every(r=>r.method==='GET'),{occurrence:handoff.request,request:detail.url()});await page.getByTestId('home-detail').getByRole('button',{name:'Close modal',exact:true}).click();
  }else checks.push({name:'Operator handoff exposure and Review target',status:'NOT_RUN',reason:'Canonical HTTP did not establish current action_required plus verify_handoff; no rights or recipient were forced.'});
  await page.getByRole('heading',{name:'Follow-up',exact:true}).evaluate(el=>el.scrollIntoView({block:'start'}));await page.screenshot({path:cfg.out+'/phase1-desktop.png',fullPage:false});
  check('Phase1 uses the frozen bundle with zero mutations or frontend errors',(await page.locator('script[src]').evaluateAll(ns=>ns.map(n=>n.src))).some(s=>s.includes(cfg.bundle))&&requests.every(r=>r.method==='GET')&&pageErrors.length===0&&consoleErrors.length===0,{pageErrors,consoleErrors});
  return{status:'PASS',checks,board,requests,responses,pageErrors,consoleErrors};
 }catch(e){await page.screenshot({path:cfg.out+'/phase1-failure.png',fullPage:false});return{status:'FAIL',message:e.message,checks,board,requests,responses,pageErrors,consoleErrors};}
}
