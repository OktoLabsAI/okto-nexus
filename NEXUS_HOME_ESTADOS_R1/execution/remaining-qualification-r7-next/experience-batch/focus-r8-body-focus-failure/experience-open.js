async page=>{
  const cfg={"window": "EXPERIENCE_FUNCTIONAL_WINDOW_OPEN", "phase": "open", "url": "http://127.0.0.1:62790", "screenshotPrefix": "C:\\Users\\jpamb\\AppData\\Local\\Temp\\nexus-hst-browser-lq4_y8ly\\experience-mobile", "aCard": "home_group_d601d98431105407a843664a4424ada69f310c83baf9d9359b873d9bb73595f9", "bCard": "home_group_e1fdbd78e2ce4d58fde63df084dd5fcde0bbcb7151fc99fd03b8615a6e2d0523", "connection": {"server_id": "srv_580484fe19a608cedbbd3bc0b58eed82", "executor_id": "exe_59eeb63ca277d772b33227d9c0ebeba6", "binding_id": "bind_c6f37977a5da74d6de80f7803dbe9dac", "endpoint_id": "ep_1183ca6fba93d0ce2b6a86b6873f4180", "agent_id": "hst-a", "workspace_id": "wsr_293d7faf764153f21888a2853d651f6c", "workspace_binding_id": "wxb_cc4f6d99a069007fca5c98364dc8c001"}, "a2Scope": {"server_id": "srv_580484fe19a608cedbbd3bc0b58eed82", "executor_id": "exe_59eeb63ca277d772b33227d9c0ebeba6", "binding_id": "bind_c6f37977a5da74d6de80f7803dbe9dac", "agent_id": "hst-a", "workspace_id": "wsr_293d7faf764153f21888a2853d651f6c", "workspace_binding_id": "wxb_cc4f6d99a069007fca5c98364dc8c001", "session_id": "ses_95416c30cdb30bcd70edcc35ee03150a", "session_owner_generation": 1, "authorization_revision": 2, "configuration_revision": 2, "binding_revision": 1, "credential_epoch": 1}, "a2Session": "ses_95416c30cdb30bcd70edcc35ee03150a", "a2Operation": "op_68ca1596a71ba553389d86f33952b5ba", "requestId": "r4request_b3a2029856ba54b097bd44b5fc8595c35eeccd9fac1be0a95a36124004c69aa9", "requestCard": "home_request_att_3968393e47d80d1f3ae804e68610d9540f56f3215384520a8f2460fcce1143f7", "attentionId": "att_3968393e47d80d1f3ae804e68610d9540f56f3215384520a8f2460fcce1143f7", "expiresAt": "2026-11-17T23:01:40.072000+00:00", "a1Session": "ses_ff482e68c8f0b8e834337ded17c8f52d", "a1Operation": "op_6cabf56d10b84b0d1ad4655c8e15c1ab"};
  if(cfg.window!=='EXPERIENCE_FUNCTIONAL_WINDOW_OPEN')throw Error('Root functional window required');
  const checks=[];
  const tupleKeys=['server_id','executor_id','binding_id','workspace_id','workspace_binding_id','agent_id'];
  const tuple=c=>Object.fromEntries(tupleKeys.map(k=>[k,c?.[k]]));
  const sameTuple=(a,b)=>tupleKeys.every(k=>a?.[k]===b?.[k]);
  const check=(id,pass,actual)=>{checks.push({id,pass:!!pass,actual});if(!pass)throw Error(id);};
  const card=id=>page.locator('[data-home-harness='+JSON.stringify(id)+']');
  const modal=page.locator('dialog[open]');
  const key=scope=>JSON.stringify([scope.server_id,scope.executor_id,scope.workspace_id,scope.session_id]);
  const alive=()=>Date.now()<Date.parse(cfg.expiresAt);
  const waitFor=async(predicate,seconds=35)=>{
    const end=Date.now()+seconds*1000;
    while(Date.now()<end){
      const found=(page.__hstFocusRecords??[]).find(predicate);if(found)return found;
      if(cfg.expiresAt&&!alive())throw Error('Original question validity elapsed; no renewal permitted');
      await page.waitForTimeout(100);
    }
    throw Error('Canonical semantic projection not observed before bounded deadline');
  };
  const containsRequest=(row,expected)=>row.requests.some(request=>request.attention_id===expected.attentionId&&request.source_id===expected.requestId&&request.session_id===expected.a2Session&&request.operation_id===expected.a2Operation)&&row.pending_request_ids.includes(expected.attentionId);
  try{
    if(cfg.phase==='initialize'){
      page.__hstFocusRecords=[];page.__hstFocusPosts=[];page.__hstFocusErrors=[];
      page.on('request',r=>{if(r.method()==='POST')page.__hstFocusPosts.push({path:new URL(r.url()).pathname});});
      page.on('pageerror',error=>page.__hstFocusErrors.push(error.message));
      // Installed before either host control. No raw DTO, CAS, prompt or answer is retained.
      page.on('response',async response=>{
        if(!new URL(response.url()).pathname.endsWith('/home/harness-board'))return;
        try{
          const raw=await response.json(),body=raw.data??raw;
          const rows=[];
          for(const [column,slice]of Object.entries(body.columns??{}))for(const item of slice.items??[]){
            if(item.kind==='harness')rows.push({kind:'harness',column,id:item.id,connection:tuple(item.connection),activity:item.operational_status?.activity,blocking:item.operational_status?.blocking,freshness:item.operational_status?.freshness,pending_request_ids:item.operational_status?.pending_request_ids??[],requests:(item.requests_preview??[]).map(x=>({attention_id:x.request?.attention_id,source_id:x.request?.source_id,session_id:x.request?.session_id,operation_id:x.request?.operation_id}))});
            else if(item.kind==='delivery')rows.push({kind:'delivery',column,id:item.id,target:item.entry?.target,sessions:(item.entry?.sessions??[]).map(s=>({server_id:s.server_id,executor_id:s.executor_id,workspace_id:s.workspace_id,session_id:s.session_id})),harness_refs:(item.harness_refs??[]).map(r=>({card_id:r.card_id,connection:tuple(r.connection)})),outcome:item.delivery_semantics?.execution_outcome});
          }
          const records=page.__hstFocusRecords;
          if(records.length>=128){page.__hstFocusOverflow=true;return;}
          records.push({revision:body.revision,status:response.status(),rows});
        }catch{/* An aborted body is not counted as received. */}
      });
      await page.addInitScript(()=>{localStorage.setItem('okto-nexus-home-operational','enabled');localStorage.setItem('okto-nexus-workspace','all');localStorage.setItem('okto-nexus:metrics-opt-in-prompt-dismissed:1.0.0',new Date().toISOString());});
      await page.goto(cfg.url);await page.getByTestId('home-follow-up').waitFor({timeout:25000});
      await card(cfg.aCard).waitFor();await card(cfg.bCard).waitFor();
      check('focus-observer-installed-before-arrival',Array.isArray(page.__hstFocusRecords),true);
    }else if(cfg.phase==='open'){
      check('question-original-validity-current',alive(),{expiresAt:cfg.expiresAt});
      await page.getByRole('button',{name:'Refresh',exact:true}).click();
      const working=await waitFor(record=>record.status===200&&record.rows.some(row=>row.kind==='harness'&&row.id===cfg.aCard&&row.column==='active'&&sameTuple(row.connection,cfg.connection)&&row.activity==='working'&&row.blocking==='partial'&&row.freshness==='current'&&containsRequest(row,cfg)));
      check('initial-canonical-working-partial-exact-request',!!working,{revision:working.revision});
      const apply=page.getByRole('button',{name:'Apply updates',exact:true});if(await apply.isVisible().catch(()=>false))await apply.click();
      await card(cfg.aCard).getByText('Working',{exact:true}).waitFor();
      await card(cfg.aCard).getByRole('button',{name:'Follow activity',exact:true}).click();await modal.waitFor();
      const selector=modal.getByRole('combobox',{name:'Choose a session',exact:true});await selector.waitFor();
      const metadata=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/runtime-management/runtime/sessions/'+cfg.a2Session&&r.request().method()==='GET',{timeout:15000});
      await selector.selectOption(key(cfg.a2Scope));const response=await metadata;const raw=await response.json(),body=raw.data??raw;
      check('known-A2-entire-current-scope',response.status()===200&&Object.keys(cfg.a2Scope).every(k=>body.scope?.[k]===cfg.a2Scope[k]),{status:response.status(),scope:body.scope});
      await modal.locator('[data-home-signal='+JSON.stringify(cfg.requestCard)+']').getByRole('button',{name:'Respond',exact:true}).click();
      await modal.getByRole('listbox',{name:'Choose fixture output format',exact:true}).waitFor();
      await page.evaluate(()=>{window.__hstFocusModal=document.querySelector('dialog[open]');});
      check('known-request-one-modal-unanswered',await modal.count()===1&&await modal.getByRole('listbox',{name:'Choose fixture output format',exact:true}).evaluate(e=>e.selectedOptions.length===0),{session:cfg.a2Session,request:cfg.requestId});
    }else if(cfg.phase==='close'){
      check('question-still-originally-valid',alive(),{expiresAt:cfg.expiresAt});
      const observed=await waitFor(record=>{
        if(record.status!==200)return false;
        const a=record.rows.filter(row=>row.kind==='harness'&&row.id===cfg.aCard);
        const delivery=record.rows.find(row=>row.kind==='delivery'&&row.id===cfg.deliveryId&&row.column==='results'&&row.outcome==='succeeded'&&row.target?.operation_id===cfg.a1Operation&&row.target?.server_id===cfg.connection.server_id&&row.target?.executor_id===cfg.connection.executor_id&&row.target?.workspace_id===cfg.connection.workspace_id&&row.sessions.some(s=>s.session_id===cfg.a1Session&&s.server_id===cfg.connection.server_id&&s.executor_id===cfg.connection.executor_id&&s.workspace_id===cfg.connection.workspace_id)&&row.harness_refs.some(r=>r.card_id===cfg.aCard&&sameTuple(r.connection,cfg.connection)));
        return a.length===1&&a[0].column==='needs_you'&&sameTuple(a[0].connection,cfg.connection)&&a[0].activity==='waiting_user'&&a[0].blocking==='full'&&a[0].freshness==='current'&&containsRequest(a[0],cfg)&&!!delivery;
      });
      check('canonical-move-request-and-terminal-delivery',true,{actualRevision:observed.revision,hostRevision:cfg.hostRevision,revisionsEqual:observed.revision===cfg.hostRevision});
      check('same-A2-panel-after-column-change',await page.evaluate(()=>window.__hstFocusModal===document.querySelector('dialog[open]'))&&await modal.getByRole('listbox',{name:'Choose fixture output format',exact:true}).count()===1,{session:cfg.a2Session,request:cfg.requestId});
      await page.keyboard.press('Escape');await modal.waitFor({state:'hidden',timeout:12000});
      const needs=page.locator('[data-home-column=needs_you]').locator('[data-home-harness='+JSON.stringify(cfg.aCard)+']');await needs.waitFor();
      const end=Date.now()+2500;let focus;
      do{focus=await page.evaluate(()=>({harness:document.activeElement?.closest('[data-home-harness]')?.getAttribute('data-home-harness'),tag:document.activeElement?.tagName,text:document.activeElement?.textContent}));if(focus.harness===cfg.aCard||(focus.tag==='H1'&&focus.text==='Home'))break;await page.waitForTimeout(50);}while(Date.now()<end);
      check('focus-return-same-A-or-stable-heading',focus.harness!==cfg.bCard&&(focus.harness===cfg.aCard||(focus.tag==='H1'&&focus.text==='Home')),focus);
      check('one-A-DOM-card-in-new-column',await card(cfg.aCard).count()===1&&await page.locator('[data-home-column=active]').locator('[data-home-harness='+JSON.stringify(cfg.aCard)+']').count()===0,{id:cfg.aCard});
    }else throw Error('Unknown phase');
    check('zero-browser-POST',page.__hstFocusPosts.length===0,page.__hstFocusPosts);check('zero-page-errors',page.__hstFocusErrors.length===0,page.__hstFocusErrors);
    return {status:'PASS_EXECUTED_SUBSET',phase:cfg.phase,checks,records:page.__hstFocusRecords,overflow:!!page.__hstFocusOverflow};
  }catch(error){
    const dom=await page.evaluate(()=>({dialogs:document.querySelectorAll('dialog[open]').length,activeIds:Array.from(document.querySelectorAll('[data-home-column=active] [data-home-harness]')).map(e=>e.getAttribute('data-home-harness')),needsIds:Array.from(document.querySelectorAll('[data-home-column=needs_you] [data-home-harness]')).map(e=>e.getAttribute('data-home-harness')),focusedHarness:document.activeElement?.closest('[data-home-harness]')?.getAttribute('data-home-harness'),focusedTag:document.activeElement?.tagName})).catch(()=>null);
    return {status:'INCOMPLETE',phase:cfg.phase,checks,records:page.__hstFocusRecords??[],overflow:!!page.__hstFocusOverflow,posts:page.__hstFocusPosts??[],errors:page.__hstFocusErrors??[],dom,error:String(error)};
  }
}
