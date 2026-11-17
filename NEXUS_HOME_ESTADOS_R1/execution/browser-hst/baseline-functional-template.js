async page=>{
 const cfg=__CONFIG__,checks=[],requests=[],responses=[],errors=[];
 const check=(id,ok,detail)=>{checks.push({id,ok,detail});if(!ok)throw Error(id+': '+JSON.stringify(detail));};
 page.on('pageerror',e=>errors.push(e.message));
 page.on('request',r=>requests.push({method:r.method(),path:new URL(r.url()).pathname,at:Date.now()}));
 page.on('response',async r=>{if(new URL(r.url()).pathname==='/api/v1/home/harness-board'){
   const payload=await r.json();responses.push({status:r.status(),at:Date.now(),revision:payload.data?.revision});}});
 try{
 const dialog=page.getByRole('dialog',{name:'Activity detail'});
 check('paused-detail-one-modal',await dialog.count()===1,await dialog.count());
 const chooser=dialog.getByRole('combobox',{name:'Choose a session'});
 const options=await chooser.locator('option').evaluateAll(v=>v.map(e=>({value:e.value,label:e.textContent})));
 const key=s=>JSON.stringify([s.reference.server_id,s.reference.executor_id,s.reference.workspace_id,s.session_id]);
 check('exact-two-session-catalog',cfg.sessions.every(s=>options.some(o=>o.value===key(s))),options);
 for(const s of cfg.sessions){
   await chooser.selectOption(key(s));
   await dialog.getByText(s.text,{exact:false}).first().waitFor({timeout:15000});
   check('exact-session-'+(s.closed?'retained':'current'),await chooser.inputValue()===key(s),s.session_id);
 }
 const selected=await chooser.inputValue();
 const focused=await dialog.locator('button').first().evaluate(e=>{e.focus();return document.activeElement===e});
 check('keyboard-focus-in-dialog',focused,true);
 const anchor=Date.now();
 await page.waitForTimeout(32000);
 const boardReads=responses.filter(r=>r.status===200);
 check('two-real-fallback-polls',boardReads.length>=2,{boardReads,elapsed:Date.now()-anchor});
 check('identical-semantic-revision',new Set(boardReads.map(r=>r.revision)).size===1,boardReads);
 check('paused-target-preserved',await chooser.inputValue()===selected,selected);
 const body=await page.locator('body').innerText();
 check('identical-polls-no-false-update',!body.includes('Updates available')&&!body.includes('Updates are available'),body.includes('Updates are available'));
 check('no-error-alert',await page.getByRole('alert').count()===0,await page.getByRole('alert').count());
 await page.keyboard.press('Escape');
 await dialog.waitFor({state:'hidden'});
 check('escape-closed-readonly-without-discard',!(await page.locator('body').innerText()).includes('Discard unsaved changes?'),true);
 await page.setViewportSize({width:360,height:800});
 const geometry=await page.evaluate(()=>({innerWidth,scrollWidth:document.documentElement.scrollWidth,
   columns:[...document.querySelectorAll('[data-home-column]')].map(e=>({name:e.getAttribute('data-home-column'),x:e.getBoundingClientRect().x,y:e.getBoundingClientRect().y,width:e.getBoundingClientRect().width}))}));
 check('mobile-no-overflow-three-stacked',geometry.scrollWidth<=geometry.innerWidth&&geometry.columns.length===3&&geometry.columns.every((c,i)=>i===0||c.y>geometry.columns[i-1].y),geometry);
 await page.getByRole('heading',{name:'Follow-up',exact:true}).scrollIntoViewIfNeeded();
 await page.screenshot({path:cfg.mobileScreenshot,fullPage:true});
 check('no-page-exceptions',errors.length===0,errors);
 check('browser-readonly',requests.every(r=>r.method==='GET'),requests.filter(r=>r.method!=='GET'));
 return {status:'PASS_SUBSET',checks,requests,responses,errors,limits:['Codex synthetic protocol only','No draft/decision case in this lane','No native zoom or screen-reader claim']};
 }catch(error){return {status:'FAIL',error:String(error),checks,requests,responses,errors,body:await page.locator('body').innerText()};}
}
