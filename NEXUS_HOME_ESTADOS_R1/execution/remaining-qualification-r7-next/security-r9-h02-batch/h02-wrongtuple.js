async page => {
  const cfg=__CONFIG__,checks=[],requests=[],targetResponses=[];
  const check=(id,ok)=>{checks.push({id,ok});if(!ok)throw Error(id);};
  page.on('request',r=>requests.push({method:r.method(),path:new URL(r.url()).pathname}));
  let injections=0;
  const route=async r=>{
    const url=new URL(r.request().url());
    if(url.pathname!=='/api/v1/home/target'){await r.continue();return;}
    injections++;
    if(injections!==1){await r.abort();return;}
    const target=JSON.parse(url.searchParams.get('target'));
    const canonical=value=>JSON.stringify(Object.fromEntries(Object.entries(value).sort(([a],[b])=>a.localeCompare(b))));
    check('exact-original-target-before-adversarial-query',canonical(target)===canonical(cfg.target));
    Object.assign(target,cfg.changes);
    url.searchParams.set('target',JSON.stringify(target));
    if(cfg.wrong_workspace)url.searchParams.set('workspace_id',cfg.wrong_workspace);
    await r.continue({url:url.toString()});
  };
  page.on('response',async response=>{
    if(new URL(response.url()).pathname==='/api/v1/home/target')
      targetResponses.push({status:response.status(),path:'/api/v1/home/target'});
  });
  try {
    check('no-prior-modal',await page.getByRole('dialog').count()===0);
    await page.route('**/api/v1/home/target?*',route);
    const pending=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/home/target',{timeout:15000});
    await page.locator('[data-home-event='+JSON.stringify(cfg.event_id)+']').getByRole('button',{name:cfg.button_name,exact:true}).click();
    const response=await pending;
    check('actual-server-denial',response.status()===cfg.expected_status);
    const value=await response.json(),serialized=JSON.stringify(value);
    check('no-error-preview-summary',value.ok===false&&!('data' in value)&&!serialized.includes('preview')&&!serialized.includes('summary')&&!serialized.includes(cfg.protected_marker));
    const dialog=page.getByRole('dialog');
    await dialog.getByRole('alert').waitFor({timeout:10000});
    check('one-query-no-replacement',injections===1);
    check('no-protected-dom',!(await dialog.innerText()).includes(cfg.protected_marker));
    check('no-runtime-controls',await dialog.getByRole('button',{name:'Review runtime action',exact:true}).count()===0);
    check('browser-read-only',requests.every(x=>['GET','HEAD','OPTIONS'].includes(x.method)));
    await dialog.getByRole('button',{name:'Close modal',exact:true}).click();
    return {status:'PASS_SUBSET',checks,requests,targetResponses,limits:['Real GET query mutation; not a fake response nor a workspace ACL claim']};
  }catch(error){return {status:'FAIL',checks,requests,targetResponses,error:String(error),diagnostics:{dialogs:await page.getByRole('dialog').evaluateAll(xs=>xs.map(x=>x.outerHTML.slice(0,100000))).catch(()=>[])}};}
  finally {await page.unroute('**/api/v1/home/target?*',route);}
}
