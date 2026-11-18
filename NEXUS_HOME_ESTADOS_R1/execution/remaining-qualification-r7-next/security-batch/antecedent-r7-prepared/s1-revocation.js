async page => {
  const cfg=__CONFIG__, checks=[], requests=[];
  const check=(id,ok,detail)=>{checks.push({id,ok,detail});if(!ok)throw Error(id);};
  page.on('request',r=>requests.push({method:r.method(),path:new URL(r.url()).pathname}));
  try {
    const reply=await page.request.get(cfg.url+'/api/v1/runtime-management/runtime/sessions/'+encodeURIComponent(cfg.live_session_id)+'?executor_id='+encodeURIComponent(cfg.reference.executor_id));
    check('exact-session-http-200',reply.status()===200,reply.status());
    const raw=await reply.json(), session=raw.data??raw;
    check('full-session-identity', ['server_id','executor_id','binding_id','workspace_id','workspace_binding_id','agent_id'].every(k=>session.scope[k]===cfg.reference[k])&&session.scope.session_id===cfg.live_session_id,session.scope);
    check('current-control-authority',session.control_available===!cfg.revoked,{control_available:session.control_available,lease_state:session.lease_state});
    if(cfg.revoked)check('canonical-lease-revoked',session.lease_state==='REVOKED',session.lease_state);
    await page.reload({waitUntil:'domcontentloaded'});
    const card=page.locator('[data-home-harness='+JSON.stringify(cfg.card_id)+']');
    await card.getByRole('button',{name:'Follow activity',exact:true}).click();
    const dialog=page.getByRole('dialog',{name:'Activity detail'});
    await dialog.waitFor();
    // Select the exact activity owning this live session. No first/latest fallback.
    const item=dialog.locator('[data-home-activity='+JSON.stringify(cfg.live_entry_id)+']');
    await item.getByRole('button',{name:/^View (session|work)$/}).click();
    const selector=dialog.getByLabel('Choose the exact session',{exact:false});
    if(await selector.count()){
      const options=await selector.locator('option').evaluateAll(items=>items.map(x=>x.value).filter(Boolean));
      const exact=options.filter(value=>JSON.parse(value).includes(cfg.live_session_id));
      check('one-exact-session-choice',exact.length===1,exact.length);
      await selector.selectOption(exact[0]);
    }
    const controls=dialog.getByRole('region',{name:'Original record and canonical controls'});
    await controls.waitFor();
    if(cfg.revoked){
      await controls.getByText('Controls are unavailable for this exact session.',{exact:false}).waitFor({timeout:10000});
      check('stale-controls-not-offered',await controls.getByRole('combobox',{name:'Runtime action',exact:true}).count()===0,true);
    }else{
      await controls.getByRole('combobox',{name:'Runtime action',exact:true}).waitFor({timeout:10000});
      check('pre-revocation-real-control-visible',true,true);
    }
    await dialog.getByRole('button',{name:'Close modal',exact:true}).click();
    check('no-productive-or-review-post',requests.every(x=>['GET','HEAD','OPTIONS'].includes(x.method)),requests);
    return {status:'PASS_SUBSET',checks,requests,limits:['No stale decision submission or same-name successor; historical reads may remain authorized','No claim that grant revocation exits the process or closes its lifecycle']};
  }catch(error){return {status:'FAIL',error:String(error),checks,requests};}
}
