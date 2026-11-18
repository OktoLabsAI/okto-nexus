// PREPARED ONLY. Real canonical fixture, native Chrome zoom already proved.
async page=>{
  const cfg=__CONFIG__;
  if(cfg.window!=='ROOT_I05_NATIVE_APP_OPEN')throw Error('I05 application gate required');
  if(new URL(cfg.url).protocol!=='http:'||new URL(cfg.url).hostname!=='127.0.0.1')throw Error('Own loopback app required');
  const checks=[],observations={};
  const check=(id,pass,actual)=>{checks.push({id,pass:!!pass,actual});if(!pass)throw Error(id);};
  const modal=page.locator('dialog[open]');
  const card=(attribute,id)=>page.locator('['+attribute+'='+JSON.stringify(id)+']');
  const measure=()=>page.evaluate(()=>({innerWidth,innerHeight,outerWidth,devicePixelRatio,visualScale:visualViewport?.scale,scrollWidth:document.documentElement.scrollWidth}));
  const collapse=async()=>{
    const header=page.getByRole('button',{name:'Collapse navigation',exact:true});
    if(await header.isVisible().catch(()=>false)){
      check('header-navigation-expanded',await header.getAttribute('aria-expanded')==='true',true);await header.click();
    }
    const nav=page.getByTestId('nav-sidebar');await nav.waitFor({state:'hidden'});
    check('navigation-hidden',await nav.getAttribute('aria-hidden')==='true',await nav.getAttribute('aria-hidden'));
  };
  const hit=async(locator,label)=>{
    await locator.scrollIntoViewIfNeeded();
    const proof=await locator.evaluate(element=>{const r=element.getBoundingClientRect(),x=r.x+r.width/2,y=r.y+r.height/2;const top=document.elementFromPoint(x,y);return {x,y,width:r.width,height:r.height,hit:top===element||element.contains(top),name:element.getAttribute('aria-label')||element.textContent};});
    check('hit-test-'+label,proof.hit&&proof.width>0&&proof.height>0,proof);await locator.click();
  };
  const close=async(attribute,id)=>{
    await hit(modal.getByRole('button',{name:'Close modal',exact:true}),'close-'+id);await modal.waitFor({state:'hidden'});
    const end=Date.now()+2500;let focus;
    do{focus=await page.evaluate(()=>({attribute:document.activeElement?.closest('[data-home-harness],[data-home-signal]')?.hasAttribute('data-home-harness')?'data-home-harness':'data-home-signal',id:document.activeElement?.closest('[data-home-harness],[data-home-signal]')?.getAttribute('data-home-harness')||document.activeElement?.closest('[data-home-signal]')?.getAttribute('data-home-signal'),tag:document.activeElement?.tagName,text:document.activeElement?.textContent}));if(focus.id===id||(focus.tag==='H1'&&focus.text==='Home'))break;await page.waitForTimeout(50);}while(Date.now()<end);
    check('same-context-focus-'+id,(focus.id===id&&focus.attribute===attribute)||(focus.tag==='H1'&&focus.text==='Home'),focus);
  };
  const validity=()=>{if(cfg.expiresAt)check('original-question-valid-'+cfg.caseName,Date.now()<Date.parse(cfg.expiresAt),{expiresAt:cfg.expiresAt});};
  try{
    if(cfg.phase==='bootstrap'){
      page.__i05Writes=[];page.__i05Errors=[];page.__i05Boards=[];
      page.on('request',r=>{if(!['GET','HEAD','OPTIONS'].includes(r.method()))page.__i05Writes.push({method:r.method(),path:new URL(r.url()).pathname});});
      page.on('pageerror',e=>page.__i05Errors.push(e.message));
      page.on('response',async response=>{
        if(!new URL(response.url()).pathname.endsWith('/home/harness-board')||response.status()!==200)return;
        try{const raw=await response.json(),body=raw.data??raw;
          page.__i05Boards.push({receivedAt:Date.now(),revision:body.revision,version:body.presentation_version,columns:Object.fromEntries(Object.entries(body.columns).map(([column,slice])=>[column,slice.items.map(item=>({id:item.id,kind:item.kind,binding:item.connection?.binding_id,activity:item.operational_status?.activity,blocking:item.operational_status?.blocking,freshness:item.operational_status?.freshness,sourceId:item.request?.source_id,session:item.request?.session_id}))]))});
        }catch{/* Aborted responses do not prove a received board. */}
      });
      await page.addInitScript(origin=>{if(location.origin!==origin)return;localStorage.setItem('okto-nexus-home-operational','enabled');localStorage.setItem('okto-nexus-workspace','all');localStorage.setItem('okto-nexus:metrics-opt-in-prompt-dismissed:1.0.0',new Date().toISOString());},new URL(cfg.url).origin);
      await page.setViewportSize({width:720,height:1000});await page.goto(cfg.url);await page.getByTestId('home-follow-up').waitFor({timeout:25000});
      observations.geometry=await measure();
      check('native200-survives-app-cookie-load',Math.abs(observations.geometry.devicePixelRatio-cfg.nativeDpr200)<.03&&Math.abs(observations.geometry.innerWidth-360)<=3&&observations.geometry.visualScale===1,observations.geometry);
      await collapse();
    }else if(cfg.phase==='case'){
      validity();const started=Date.now();
      await page.setViewportSize({width:cfg.requestedWidth,height:1000});await page.goto(cfg.url);await page.getByTestId('home-follow-up').waitFor({timeout:25000});await collapse();
      await page.getByRole('button',{name:'Refresh',exact:true}).click();
      const deadline=Math.min(Date.now()+20000,Date.parse(cfg.expiresAt));let current;
      do{current=(page.__i05Boards??[]).find(record=>record.receivedAt>=started&&record.version===2&&record.columns.active.some(item=>item.id===cfg.aCard&&item.activity==='working'&&item.blocking==='partial'&&item.freshness==='current')&&record.columns.needs_you.some(item=>item.id===cfg.requestCard&&item.sourceId===cfg.requestId&&item.session===cfg.a2Scope.session_id)&&record.columns.results.some(item=>item.id===cfg.deliveryId));if(current)break;await page.waitForTimeout(100);}while(Date.now()<deadline);
      check('current-three-category-canonical-board-'+cfg.caseName,!!current,current);
      const apply=page.getByRole('button',{name:'Apply updates',exact:true});if(await apply.isVisible().catch(()=>false))await apply.click();
      observations.geometry=await measure();
      check('native-zoom-and-CSS360-'+cfg.caseName,Math.abs(observations.geometry.devicePixelRatio-cfg.expectedDpr)<.03&&Math.abs(observations.geometry.innerWidth-360)<=3&&observations.geometry.visualScale===1,{requestedWidth:cfg.requestedWidth,...observations.geometry});
      const columns=page.locator('[data-home-column]');const boxes=await columns.evaluateAll(nodes=>nodes.map(e=>{const r=e.getBoundingClientRect();return {column:e.getAttribute('data-home-column'),x:r.x,y:r.y,width:r.width,height:r.height,bottom:r.bottom};}));
      check('three-stacked-columns-'+cfg.caseName,boxes.length===3&&boxes.every((b,i)=>b.width>0&&b.width<=observations.geometry.innerWidth+1&&Math.abs(b.x-boxes[0].x)<=1&&(!i||b.y>=boxes[i-1].bottom)),boxes);
      check('no-page-horizontal-overflow-'+cfg.caseName,observations.geometry.scrollWidth<=observations.geometry.innerWidth+1,observations.geometry);
      const labelRows=await page.locator('[data-home-harness],[data-home-signal]').allTextContents();
      check('real-long-project-labels-'+cfg.caseName,labelRows.every(text=>text.includes('Project:'))&&labelRows.some(text=>text.includes(cfg.projectA))&&labelRows.some(text=>text.includes(cfg.projectB)),labelRows);
      for(const name of ['active','needs_you','results']){await page.locator('[data-home-column='+name+']').getByRole('heading',{level:3}).scrollIntoViewIfNeeded();await page.screenshot({path:cfg.outputPrefix+'-'+cfg.caseName+'-'+name+'.png'});}

      // Active: actual exact singleton API and retained output, never latest selection.
      const metadata=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/runtime-management/runtime/sessions/'+cfg.bScope.session_id&&r.request().method()==='GET',{timeout:15000}).then(response=>({response})).catch(error=>({error:String(error)}));
      await hit(card('data-home-harness',cfg.bCard).getByRole('button',{name:'Follow activity',exact:true}),'active-'+cfg.caseName);
      const read=await metadata;check('active-metadata-observed-'+cfg.caseName,!!read.response,read.error??true);
      const response=read.response,raw=await response.json(),body=raw.data??raw;
      check('active-exact-full-scope-'+cfg.caseName,response.status()===200&&Object.keys(cfg.bScope).every(key=>body.scope?.[key]===cfg.bScope[key]),{status:response.status(),scope:body.scope});
      await modal.getByText(cfg.bMarker,{exact:false}).first().waitFor();await close('data-home-harness',cfg.bCard);

      // Needs you: inspect only. Do not select an answer, submit, mark seen or snooze.
      await hit(card('data-home-signal',cfg.requestCard).getByRole('button',{name:'Respond',exact:true}),'needs-you-'+cfg.caseName);
      const decision=modal.getByRole('region',{name:'Native runtime decision',exact:true});await decision.waitFor();
      await decision.getByText('Session '+cfg.a2Scope.session_id,{exact:false}).waitFor();
      const input=decision.getByRole('listbox',{name:'Choose fixture output format',exact:true});await input.waitFor();
      check('request-same-known-session-unanswered-'+cfg.caseName,await input.evaluate(e=>e.selectedOptions.length===0),{requestId:cfg.requestId,session:cfg.a2Scope.session_id});
      await close('data-home-signal',cfg.requestCard);

      // Results: open the exact authoritative detail target; no result mutation.
      await hit(card('data-home-signal',cfg.deliveryId).getByRole('button',{name:'View result',exact:true}),'results-'+cfg.caseName);
      await modal.waitFor();const target=JSON.parse(new URL(page.url()).searchParams.get('home_target')||'null');
      check('delivery-exact-target-'+cfg.caseName,!!target&&Object.keys(cfg.deliveryTarget).every(key=>target[key]===cfg.deliveryTarget[key]),target);
      await close('data-home-signal',cfg.deliveryId);
      check('project-scope-preserved-'+cfg.caseName,await page.getByRole('combobox',{name:'Project',exact:true}).inputValue()==='all',true);
      validity();
    }else throw Error('Unknown I05 phase');
    check('zero-browser-writes',page.__i05Writes.length===0,page.__i05Writes);check('zero-page-errors',page.__i05Errors.length===0,page.__i05Errors);
    return {status:'PASS_I05_EXECUTED_SUBSET',phase:cfg.phase,caseName:cfg.caseName,checks,observations,limits:['No AT speech or I01 expansion','All provider/runtime events are explicit inert-protocol fixtures','720 requested at200% and360 requested at100% both measured CSS360; not360outer at200%']};
  }catch(error){
    return {status:'INCOMPLETE_I05_APP',phase:cfg.phase,caseName:cfg.caseName,checks,observations,error:String(error),writes:page.__i05Writes??[],errors:page.__i05Errors??[],geometry:await measure().catch(()=>null)};
  }
}
