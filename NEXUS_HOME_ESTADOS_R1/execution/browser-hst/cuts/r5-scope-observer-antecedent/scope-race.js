async page=>{
 const cfg={"url": "http://127.0.0.1:62089", "a": {"server_id": "srv_583595d35ae584b95b7aea1c6c8c41f8", "executor_id": "exe_d3b0724d915a60566951d113bac21354", "binding_id": "bind_7eaf500d3bf9cfda9edcedf20afc56af", "endpoint_id": "ep_502dfdea3e5eefefcbd7335adb4d2a7d", "agent_id": "hst-a", "workspace_id": "wsr_1222780cfdcf52374a7f025ba7d4493c", "workspace_binding_id": "wxb_31def0245c63b7aea8f485debc7572dc", "session_id": "ses_f64bfa0d524c4e56a730fc45799a4c5f", "text": "HST synthetic output ses_f64bfa0d524c4e56a730fc45799a4c5f"}, "b": {"server_id": "srv_583595d35ae584b95b7aea1c6c8c41f8", "executor_id": "exe_d3b0724d915a60566951d113bac21354", "binding_id": "bind_ec64bd1716a7c413bad348f5f1be03fe", "endpoint_id": "ep_20199c76787f84e1faaf978df1e3acae", "agent_id": "hst-b", "workspace_id": "wsr_4122abf7fbef65e701460863264ee4d4", "workspace_binding_id": "wxb_d78d91bc78f95efa151939de97044d2b", "session_id": "ses_f343cd2a100ef0796520e9aad2681206", "text": "HST synthetic output ses_f343cd2a100ef0796520e9aad2681206"}, "screenshot": "D:\\Projetos\\Techridy\\okto_labs_okto_nexus\\output\\playwright\\home-states\\r5-scope-race.png"},checks=[],deliveries=[];let releaseA,heldA,oldFetchInstalled=false;
 const pattern='**/api/v1/home/harness-board?*';
 const check=(id,ok,detail)=>{checks.push({id,ok,detail});if(!ok)throw Error(id);};
 const digest=async bytes=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))).map(x=>x.toString(16).padStart(2,'0')).join('');
 const gate=new Promise(resolve=>{releaseA=resolve;});
 let capturedResolve;const captured=new Promise(resolve=>{capturedResolve=resolve;});
 const routeHandler=async route=>{
  const url=new URL(route.request().url());
  if(url.searchParams.get('workspace_id')!==cfg.a.workspace_id)return route.continue();
  const response=await route.fetch();const bytes=await response.body();
  heldA={capturedAt:Date.now(),status:response.status(),sha256:await digest(bytes)};capturedResolve();
  await gate;
  await route.fulfill({response});
 };
 try{
  const r=await page.request.get(cfg.url+'/api/v1/home/harness-board?presentation_version=2');
  const all=(await r.json()).data;
  const cards=Object.values(all.columns).flatMap(c=>c.items).filter(x=>x.kind==='harness');
  const a=cards.find(x=>x.connection.workspace_id===cfg.a.workspace_id),b=cards.find(x=>x.connection.workspace_id===cfg.b.workspace_id);
  check('same-public-id-two-canonical-projects',cards.length===2&&a.connection.connect_id==='reviewer'&&b.connection.connect_id==='reviewer'&&a.id!==b.id,cards.map(x=>({id:x.id,project:x.connection.workspace_id,label:x.connection.workspace_label})));
  await page.getByRole('combobox',{name:'Project',exact:true}).selectOption('all');
  await page.locator('[data-home-harness="'+a.id+'"]').waitFor();
  await page.locator('[data-home-harness="'+b.id+'"]').waitFor();
  check('all-project-cards-labeled',(await page.locator('[data-home-harness="'+a.id+'"]').innerText()).includes(a.connection.workspace_label)&&(await page.locator('[data-home-harness="'+b.id+'"]').innerText()).includes(b.connection.workspace_label),true);
  check('compact-three-column-navigation',await page.locator('[data-home-column]').count()===3&&await page.getByRole('button',{name:/^Reconnect/}).count()===0,true);
  await page.evaluate(({workspace})=>{
   window.__hstOriginalFetch=window.fetch;
   window.fetch=(input,init)=>{
    const address=typeof input==='string'?input:input instanceof URL?input.href:input.url;
    if(!address)return window.__hstOriginalFetch(input,init);
    const url=new URL(address,location.href);
    if(url.pathname==='/api/v1/home/harness-board'&&url.searchParams.get('workspace_id')===workspace)
     return window.__hstOriginalFetch(input,{...(init??{}),signal:new AbortController().signal});
    return window.__hstOriginalFetch(input,init);
   };
  },{workspace:cfg.a.workspace_id});oldFetchInstalled=true;
  await page.route(pattern,routeHandler);
  page.on('response',async response=>{
   const url=new URL(response.url());
   if(url.pathname!=='/api/v1/home/harness-board')return;
   deliveries.push({scope:url.searchParams.get('workspace_id'),at:Date.now(),status:response.status(),sha256:await digest(await response.body())});
  });
  await page.getByRole('combobox',{name:'Project',exact:true}).selectOption(cfg.a.workspace_id);
  await Promise.race([captured,page.waitForTimeout(10000).then(()=>{throw Error('A canonical response was not captured');})]);
  await page.getByRole('combobox',{name:'Project',exact:true}).selectOption(cfg.b.workspace_id);
  await page.locator('[data-home-harness="'+b.id+'"]').waitFor({timeout:15000});
  await page.locator('[data-home-harness="'+b.id+'"]').getByRole('button',{name:'Follow activity',exact:true}).click();
  const dialog=page.getByRole('dialog',{name:'Activity detail'});
  await dialog.getByText(cfg.b.text,{exact:false}).first().waitFor({timeout:10000});
  check('singleton-direct-exact-session',await dialog.getByRole('combobox',{name:/session/i}).count()===0&&(await dialog.innerText()).includes(cfg.b.session_id),cfg.b.session_id);
  const bDelivered=deliveries.find(x=>x.scope===cfg.b.workspace_id&&x.status===200);
  check('b-real-response-before-a-release',!!bDelivered&&heldA.status===200,{heldA,bDelivered});
  releaseA();
  for(let i=0;i<100&&!deliveries.some(x=>x.scope===cfg.a.workspace_id);i++)await page.waitForTimeout(50);
  const aDelivered=deliveries.find(x=>x.scope===cfg.a.workspace_id&&x.status===200);
  check('late-a-byte-identical-after-b',!!aDelivered&&aDelivered.at>bDelivered.at&&aDelivered.sha256===heldA.sha256,{heldA,aDelivered,bDelivered});
  await page.waitForTimeout(200);
  check('b-scope-and-context-survive-late-a',await page.getByRole('combobox',{name:'Project',exact:true}).inputValue()===cfg.b.workspace_id&&(await dialog.innerText()).includes(cfg.b.text)&&!(await dialog.innerText()).includes(cfg.a.text),true);
  check('no-a-card-leaked',await page.locator('[data-home-harness="'+a.id+'"]').count()===0,true);
  await page.screenshot({path:cfg.screenshot,fullPage:false});
  return {status:'PASS_SUBSET',checks,deliveries,heldA,b_card_id:b.id,limits:['Test-only abort-resistant GET A plus delayed unchanged canonical response; not natural network behavior','Two own synthetic Codex connections; no provider/native-family claim']};
 }catch(error){return {status:'FAIL',error:String(error),checks,deliveries,heldA,body:await page.locator('body').innerText()};}
 finally{
  releaseA();await page.unroute(pattern,routeHandler);
  if(oldFetchInstalled)await page.evaluate(()=>{window.fetch=window.__hstOriginalFetch;delete window.__hstOriginalFetch;});
 }
}
