// PREPARED ONLY: real Tab/Shift+Tab/Enter/Escape; no mouse activation or decisions.
async page=>{
  const cfg={"window": "ROOT_I01_KEYBOARD_APP_OPEN", "phase": "case", "url": "http://127.0.0.1:55394", "outputPrefix": "C:\\Users\\jpamb\\AppData\\Local\\Temp\\nexus-hst-browser-y0gtl06t\\i01-app", "expiresAt": "2026-11-18T01:58:34.941000+00:00", "aCard": "home_group_3b62b813f4dce788813c0a5d8f620b2f64fb38e0b09d41df89c2338f6ddb3fd4", "bCard": "home_group_734e8c89be5fb061ad702ee94b4a9d25407330111970fe583fffdbc200292169", "bScope": {"server_id": "srv_244f627155b054627d4368f84f29181c", "executor_id": "exe_b0fd3ed6f8864e985533e03344414a87", "binding_id": "bind_16ef54e695132d7c1a5acb1e7f0d60ba", "agent_id": "hst-b", "workspace_id": "wsr_242db860f389d71530a9101527e71f94", "workspace_binding_id": "wxb_39289aa45530facf100b069d95b50d3f", "session_id": "ses_feefb334f9f9e752dcabd3c089cf062c", "session_owner_generation": 1, "authorization_revision": 2, "configuration_revision": 2, "binding_revision": 1, "credential_epoch": 1}, "bMarker": "HST synthetic output ses_feefb334f9f9e752dcabd3c089cf062c", "a2Scope": {"server_id": "srv_244f627155b054627d4368f84f29181c", "executor_id": "exe_b0fd3ed6f8864e985533e03344414a87", "binding_id": "bind_38873af2d9aaa2dc9b77a1f75a70403e", "agent_id": "hst-a", "workspace_id": "wsr_34a0118ef7d883b272779453e0c7712b", "workspace_binding_id": "wxb_f42be19d619f39b30ead885ccb8726f4", "session_id": "ses_9436fe637b4a2c2c98680d1526b7f0e6", "session_owner_generation": 1, "authorization_revision": 2, "configuration_revision": 2, "binding_revision": 1, "credential_epoch": 1}, "requestCard": "home_request_att_e3263463eff6ee648cd5f23d7a7bcb4508a0640b0b0384e3834d999956a3be75", "requestId": "r4request_95b3c80074ff52189c5ac61fd2f44e0f9b05cd8bdf29ad7ce8a7251043d8b314", "deliveryId": "home_delivery_canonical:result_f8b11e4cf2be9028c9e4c1cb360d798e7d271cfab7b7552711b395a1dcb5de7a", "deliveryTarget": {"executor_id": "exe_b0fd3ed6f8864e985533e03344414a87", "kind": "result", "operation_id": "op_525aa52925efc2b0700aa750c017c35c", "server_id": "srv_244f627155b054627d4368f84f29181c", "session_id": "ses_feefb334f9f9e752dcabd3c089cf062c", "workspace_id": "wsr_242db860f389d71530a9101527e71f94"}, "projectA": "Alpha project for readable authorized collaborator activity and questions", "projectB": "Beta project for readable authorized collaborator activity and delivery"},checks=[],records=[];
  if(cfg.window!=='ROOT_I01_KEYBOARD_APP_OPEN'||new URL(cfg.url).hostname!=='127.0.0.1')throw Error('Own I01 gate required');
  const check=(id,pass,actual)=>{checks.push({id,pass:!!pass,actual});if(!pass)throw Error(id);};
  const modal=page.locator('dialog[open]');
  const pathOf=e=>{const parts=[];for(let n=e;n&&n!==document.body;n=n.parentElement){const siblings=Array.from(n.parentElement?.children??[]);parts.unshift(n.tagName+':'+siblings.indexOf(n));}return parts.join('/');};
  const focused=async()=>{
    const f=await page.evaluate(fn=>{
      const e=document.activeElement,d=document.querySelector('dialog[open]'),path=Function('return ('+fn+')')(),s=e?getComputedStyle(e):null,r=e?.getBoundingClientRect();
      return {path:e?path(e):null,tag:e?.tagName,type:e?.getAttribute('type'),hasFocus:document.hasFocus(),focusCountDOM:document.querySelectorAll(':focus').length,activeMatchesFocus:e?.matches(':focus'),modalOpen:!!d,uaModal:!!d?.matches(':modal'),focusVisible:e?.matches(':focus-visible'),paintedFocus:s?((s.outlineStyle!=='none'&&parseFloat(s.outlineWidth)>0)||s.boxShadow!=='none'):false,outline:s?.outlineStyle,outlineWidth:s?.outlineWidth,shadow:s?.boxShadow,visible:!!r&&r.width>0&&r.height>0,inModal:!!e?.closest('dialog[open]'),homeId:e?.closest('[data-home-harness],[data-home-signal]')?.getAttribute('data-home-harness')||e?.closest('[data-home-signal]')?.getAttribute('data-home-signal'),focusEvents:(window.__i01FocusEvents??[]).splice(0)};
    },String(pathOf));
    f.focusCountLocator=await page.locator(':focus').count();return f;
  };
  const nameProof=async locator=>{
    const ax=await locator.ariaSnapshot(),first=ax.split('\n')[0];
    const shape=await locator.evaluate(e=>{
      const interactive=new Set(['button','link','checkbox','radio','switch','textbox','searchbox','combobox','listbox','option','slider','spinbutton','tab','menuitem','menuitemcheckbox','menuitemradio','treeitem']);
      const childAction=!!e.querySelector('button,a[href],input,select,textarea,summary,[tabindex],[contenteditable]')||Array.from(e.querySelectorAll('[role]')).some(n=>interactive.has(n.getAttribute('role')));
      const s=getComputedStyle(e);
      return {tag:e.tagName,role:e.getAttribute('role'),tabindex:e.getAttribute('tabindex'),editable:e.isContentEditable,childAction,overflowY:s.overflowY,scrollHeight:e.scrollHeight,clientHeight:e.clientHeight,insideDialog:!!e.closest('dialog[open]')};
    });
    if(shape.tag==='PRE'){
      const content=await locator.evaluate(async(e,axText)=>{
        const enc=new TextEncoder(),text=enc.encode(e.textContent??''),ax=enc.encode(axText);
        const digest=async bytes=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))).map(n=>n.toString(16).padStart(2,'0')).join('');
        return {textNonempty:!!e.textContent?.trim(),axNonempty:!!axText.trim(),textBytes:text.length,axBytes:ax.length,textSha256:await digest(text),axSha256:await digest(ax)};
      },ax);
      const parentAX=(await modal.ariaSnapshot()).split('\n')[0];
      const parentNamed=/^- dialog "[^"\n]+"/.test(parentAX);
      const staticScrollable=shape.role===null&&shape.tabindex===null&&!shape.editable&&!shape.childAction&&shape.insideDialog&&['auto','scroll'].includes(shape.overflowY)&&shape.scrollHeight>shape.clientHeight&&content.textNonempty&&content.axNonempty&&parentNamed;
      // Do not serialize the technical payload or CAS into the observation.
      return {named:false,staticScrollable,shape,content,parentAX};
    }
    const summary=shape.tag==='SUMMARY';
    const named=/^- [\w-]+ "[^"\n]+"/.test(first)||(summary&&/^- (text|generic): \S/.test(first));
    return {ax:first,named,summaryContentName:summary,staticScrollable:false};
  };
  const scrollStaticPre=async(locator,label)=>{
    const snap=()=>locator.evaluate(e=>({top:e.scrollTop,max:e.scrollHeight-e.clientHeight,focused:document.hasFocus()&&e===document.activeElement&&e.matches(':focus'),windowY:scrollY,selectionLength:getSelection()?.toString().length??0,selectCounts:Array.from(e.closest('dialog').querySelectorAll('select')).map(n=>n.selectedOptions.length)}));
    const settle=async()=>{
      const end=Date.now()+1500;let last=null,stable=0,value;
      do{value=await snap();if(last!==null&&Math.abs(value.top-last)<.1)stable++;else stable=0;last=value.top;if(stable>=3)return value;await page.waitForTimeout(40);}while(Date.now()<end);
      return value;
    };
    const before=await settle(),writesBefore=page.__i01Writes.length;
    check(label+'-pre-scroll-precondition',before.focused&&before.top<before.max,before);
    await page.keyboard.press('ArrowDown');const down=await settle();
    check(label+'-ArrowDown-scrolls-own-pre',down.focused&&down.top>before.top&&Math.abs(down.windowY-before.windowY)<=1,{before,down});
    await page.keyboard.press('ArrowUp');const up=await settle();
    check(label+'-ArrowUp-restores-own-pre',up.focused&&up.top<down.top&&Math.abs(up.top-before.top)<=2&&Math.abs(up.windowY-before.windowY)<=1,{before,up});
    check(label+'-arrows-no-selection-or-request-write',before.selectionLength===0&&down.selectionLength===0&&up.selectionLength===0&&JSON.stringify(before.selectCounts)===JSON.stringify(down.selectCounts)&&JSON.stringify(before.selectCounts)===JSON.stringify(up.selectCounts)&&page.__i01Writes.length===writesBefore,{selectionLengths:[before.selectionLength,down.selectionLength,up.selectionLength],selectCounts:[before.selectCounts,down.selectCounts,up.selectCounts],writesBefore,writesAfter:page.__i01Writes.length});
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
    const dialogName=await nameProof(modal);check(label+'-dialog-accessible-name',dialogName.named,dialogName);
    const staticProbed=new Set();
    const inventory=await inventoryOf(modal);check(label+'-modal-controls-nonempty',inventory.length>0,inventory.length);
    const visited=[],cycle=[];
    const observe=async step=>{
      const f=await focused();let n=null;
      if(f.hasFocus&&f.activeMatchesFocus&&f.focusCountDOM===1&&f.focusCountLocator===1)n=await nameProof(page.locator(':focus'));
      const outsideDocument=f.hasFocus===false&&f.focusCountDOM===0&&f.focusCountLocator===0&&f.activeMatchesFocus===false&&f.modalOpen&&f.uaModal;
      records.push({phase:label,step,focus:f,name:n,outsideDocument});cycle.push({step,focus:f,name:n,outsideDocument});
      check(label+'-no-background-focus-event-'+step,!f.focusEvents.some(e=>e.event==='focusin'&&e.modalOpen&&!e.targetInModal),f.focusEvents);
      check(label+'-native-modal-focus-state-'+step,f.modalOpen&&f.uaModal&&(outsideDocument||(f.hasFocus&&f.activeMatchesFocus&&f.focusCountDOM===1&&f.focusCountLocator===1&&f.inModal&&f.visible&&f.focusVisible&&f.paintedFocus&&(n?.named||n?.staticScrollable))),{focus:f,name:n,outsideDocument});
      if(n?.staticScrollable&&!staticProbed.has(f.path)){
        await scrollStaticPre(page.locator(':focus'),label+'-'+step);staticProbed.add(f.path);
      }
      if(!outsideDocument&&!visited.includes(f.path))visited.push(f.path);
      return {f,outsideDocument};
    };
    // Count the actual initial focus rather than Tab past the first control.
    await observe('initial');
    for(let i=0;i<90&&!inventory.every(p=>visited.includes(p));i++){
      await page.keyboard.press('Tab');await observe('Tab-'+i);
    }
    check(label+'-all-enabled-modal-controls-covered',inventory.every(p=>visited.includes(p)),{inventory,visited,missing:inventory.filter(p=>!visited.includes(p)),cycle});
    for(const key of ['Tab','Shift+Tab']){
      await page.keyboard.press(key);let state=await observe('boundary-'+key);
      // Bounded benign navigation can return from browser-level focus; never focus() or trap.
      for(let i=0;i<6&&state.outsideDocument;i++){
        await page.keyboard.press(key);state=await observe('return-'+key+'-'+i);
      }
      check(label+'-returned-to-dialog-'+key,!state.outsideDocument&&state.f.inModal,state.f);
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
      await page.addInitScript(origin=>{
        if(location.origin!==origin)return;
        localStorage.setItem('okto-nexus-home-operational','enabled');localStorage.setItem('okto-nexus-workspace','all');localStorage.setItem('okto-nexus:metrics-opt-in-prompt-dismissed:1.0.0',new Date().toISOString());
        window.__i01FocusEvents=[];
        const capture=(event,target)=>{
          const d=document.querySelector('dialog[open]'),e=document.activeElement;
          window.__i01FocusEvents.push({event,time:performance.now(),hasFocus:document.hasFocus(),focusCountDOM:document.querySelectorAll(':focus').length,activeTag:e?.tagName,activeMatchesFocus:e?.matches(':focus'),modalOpen:!!d,uaModal:!!d?.matches(':modal'),targetTag:target?.tagName??null,targetInModal:!!target?.closest?.('dialog[open]')});
        };
        for(const name of ['focusin','focusout','focus','blur'])document.addEventListener(name,event=>capture(name,event.target),true);
        for(const name of ['focus','blur'])window.addEventListener(name,()=>capture('window-'+name,null));
      },new URL(cfg.url).origin);
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
