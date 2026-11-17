async page=>{
 const cfg=__CFG__,checks=[],requests=[],errors=[];
 page.setDefaultTimeout(7000);
 page.on('dialog',async d=>{if(d.type()==='beforeunload')await d.accept();else errors.push('Unexpected dialog: '+d.type());});
 const check=(name,ok,data={})=>{checks.push({name,status:ok?'PASS':'FAIL',...data});if(!ok)throw Error(name);};
 page.on('request',r=>requests.push({method:r.method(),path:new URL(r.url()).pathname}));
 page.on('pageerror',e=>errors.push(e.message));
 const get=async path=>{const r=await page.request.get(cfg.url+path,{headers:{'X-Nexus-UI':'1'}});check('GET '+path.split('?')[0],r.status()===200,{http_status:r.status()});const value=await r.json();return value.data??value;};
 const dismiss=async()=>{const button=page.getByRole('button',{name:'Close metrics settings',exact:true});if(await button.isVisible())await button.click();};
 try{
  await dismiss();
  await page.getByRole('heading',{name:'Harness ID: '+cfg.connect_id,exact:true}).waitFor();
  const binding=await get('/api/v1/runtime-management/connections/bindings/'+cfg.reference.binding_id);
  check('One registered Harness ID retains full canonical connection',Object.entries(cfg.reference).every(([k,v])=>binding[k]===v)&&await page.getByRole('heading',{name:'Harness ID: '+cfg.connect_id,exact:true}).count()===1);
  await page.screenshot({path:'output/playwright/qc31/home.png',fullPage:false});
  for(const session of cfg.sessions){
   const target={kind:'session',server_id:cfg.reference.server_id,executor_id:cfg.reference.executor_id,workspace_id:cfg.reference.workspace_id,session_id:session.session_id};
   const resolved=await get('/api/v1/home/target?'+new URLSearchParams({target:JSON.stringify(target),workspace_id:cfg.reference.workspace_id}));
   check('Canonical target '+session.label+' selects exact session',resolved.available===true&&resolved.session_context.session_id===session.session_id&&resolved.session_context.binding_id===cfg.reference.binding_id,{context:resolved.session_context});
   // Open the exact deep link in a fresh own tab. A full navigation away from
   // a mounted terminal raises beforeunload, which interrupts CLI run-code.
   const context=page.context();
   await page.close();
   page=await context.newPage();
   page.setDefaultTimeout(7000);
   page.on('request',r=>requests.push({method:r.method(),path:new URL(r.url()).pathname}));
   page.on('pageerror',e=>errors.push(e.message));
   await page.goto(cfg.url+'/?'+new URLSearchParams({home_target:JSON.stringify(target)}),{waitUntil:'domcontentloaded'});
   await dismiss();
   const output=page.getByRole('region',{name:'Session execution output',exact:true});
   await output.waitFor();
   await dismiss();
   check('Only exact output region '+session.label,await output.count()===1&&(await output.innerText()).includes(session.session_id));
   await output.getByRole('button',{name:'History',exact:true}).click();
   await page.waitForFunction(text=>document.body.innerText.includes(text),session.text,{timeout:7000});
   const text=await output.innerText();
   const other=cfg.sessions.find(s=>s.session_id!==session.session_id);
   check('History '+session.label+' never falls through to latest/sibling',text.includes(session.text)&&!text.includes(other.text),{session_id:session.session_id,text});
   const events=await get('/api/v1/runtime-management/runtime/sessions/'+session.session_id+'/events?'+new URLSearchParams({executor_id:cfg.reference.executor_id,after_sequence:'0',limit:'100'}));
   check('Real events '+session.label+' match only requested session',events.scope.session_id===session.session_id&&JSON.stringify(events).includes(session.text)&&!JSON.stringify(events).includes(other.text),{scope:events.scope,stream_epoch:events.stream_epoch,events:events.events.length});
   await page.screenshot({path:'output/playwright/qc31/session-'+session.label+'.png',fullPage:false});
  }
  check('Distinct session IDs and only GET observation',cfg.sessions[0].session_id!==cfg.sessions[1].session_id&&requests.every(r=>['GET','HEAD','OPTIONS'].includes(r.method))&&errors.length===0,{errors});
  return{status:'PASS',checks,requests,errors};
 }catch(e){await page.screenshot({path:'output/playwright/qc31/failure.png',fullPage:false});return{status:'FAIL',message:e.message,checks,requests,errors};}
}
