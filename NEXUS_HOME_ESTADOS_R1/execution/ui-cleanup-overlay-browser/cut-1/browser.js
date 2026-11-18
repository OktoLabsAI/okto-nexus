async page=>{
 const cfg={"url": "http://127.0.0.1:57418", "card": "home_group_144531ea79ecc380642cb554cb43495fc1a8d4ce782d35cae86850e903922283", "event": "work:home_ef0ced755d211897cc3245bd114ff3deec36f742ed9e7b4d19411a6b39b43ef7", "target": {"executor_id": "exe_9d318af05764d792710964dbc3b713a7", "kind": "execution", "operation_id": "op_ac82a5ee57baedc694c959071ca8c5b0", "server_id": "srv_f6b5e9c68e87a59ccdd2b46049b70541", "session_id": "ses_61800168e0bc79092d582b504b0e6a29", "workspace_id": "wsr_aacb9821570fc3b3ef51e08e11be4ce5"}, "scope": {"server_id": "srv_f6b5e9c68e87a59ccdd2b46049b70541", "executor_id": "exe_9d318af05764d792710964dbc3b713a7", "binding_id": "bind_eceb2481a307d99aecea9677c2951442", "agent_id": "hst-a", "workspace_id": "wsr_aacb9821570fc3b3ef51e08e11be4ce5", "workspace_binding_id": "wxb_b5ddab789e15f3ed18928ab5d1c04471", "session_id": "ses_61800168e0bc79092d582b504b0e6a29", "session_owner_generation": 1, "authorization_revision": 2, "configuration_revision": 2, "binding_revision": 1, "credential_epoch": 1}, "output": "C:\\Users\\jpamb\\AppData\\Local\\Temp\\nexus-hst-browser-8j4p75a3\\overlay"},checks=[];const check=(id,pass,actual)=>{checks.push({id,pass:!!pass,actual});if(!pass)throw Error(id);};
 try{
  page.__overlayWrites=[];page.__overlayErrors=[];page.on('request',r=>{if(!['GET','HEAD','OPTIONS'].includes(r.method()))page.__overlayWrites.push({method:r.method(),path:new URL(r.url()).pathname});});page.on('pageerror',e=>page.__overlayErrors.push(e.message));
  await page.addInitScript(origin=>{if(location.origin!==origin)return;localStorage.setItem('okto-nexus-home-operational','enabled');localStorage.setItem('okto-nexus-workspace','all');localStorage.setItem('okto-nexus:metrics-opt-in-prompt-dismissed:1.0.0',new Date().toISOString());},new URL(cfg.url).origin);
  await page.setViewportSize({width:1440,height:1000});await page.goto(cfg.url);await page.getByTestId('home-follow-up').waitFor({timeout:20000});
  check('actual-new-asset',await page.locator('script[src*="index-Cp1x7DiS.js"]').count()===1,true);
  const home=page.getByTestId('home-follow-up');await home.locator('[data-home-harness='+JSON.stringify(cfg.card)+']').waitFor();
  check('home-no-connection-details-or-evidence-time',!/(Connection details|Evidence observed)/.test(await home.innerText()),true);
  check('home-no-generic-work-request-heading',await home.getByText('Work request',{exact:true}).count()===0,true);
  const times=await home.locator('time').evaluateAll(nodes=>nodes.map(e=>{const value=e.getAttribute('datetime');return {datetime:value,text:e.textContent,expected:new Intl.DateTimeFormat('en-US',{month:'short',day:'2-digit',hour:'2-digit',minute:'2-digit'}).format(new Date(value)),zone:Intl.DateTimeFormat().resolvedOptions().timeZone};}));
  check('local-time-preserves-datetime',times.length>0&&times.every(t=>t.datetime&&t.text===t.expected&&t.text!==t.datetime),times);
  await page.screenshot({path:cfg.output+'-home.png'});
  const metadata=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/runtime-management/runtime/sessions/'+cfg.scope.session_id&&r.request().method()==='GET',{timeout:15000}).then(response=>({response})).catch(e=>({error:String(e)}));
  await page.locator('[data-home-event='+JSON.stringify(cfg.event)+']').getByRole('button',{name:'View work',exact:true}).click();
  const modal=page.locator('dialog[open]');await modal.waitFor();const observed=await metadata;check('exact-session-GET',!!observed.response,observed.error??true);
  const raw=await observed.response.json(),data=raw.data??raw;check('full-scope-unchanged',observed.response.status()===200&&Object.keys(cfg.scope).every(k=>data.scope?.[k]===cfg.scope[k]),{status:observed.response.status(),scope:data.scope});
  const target=JSON.parse(new URL(page.url()).searchParams.get('home_target')||'null');check('View-work-exact-target',!!target&&Object.keys(cfg.target).every(k=>target[k]===cfg.target[k]),target);
  const output=modal.getByRole('region',{name:'Session execution output',exact:true});await output.waitFor();await output.getByText('Turn started',{exact:true}).first().waitFor({timeout:12000});
  const visible=await modal.innerText(),ids=Object.values(cfg.scope).filter(v=>typeof v==='string'&&/^(ses_|srv_|exe_|bind_|wxb_|wsr_)/.test(v));
  check('technical-identities-not-in-basic-visible-text',ids.every(id=>!visible.includes(id)),{checked:ids.length});
  check('real-READY-controls',data.lifecycle_state==='READY'&&data.control_available===true&&!data.durable_release_pending,{state:data.lifecycle_state,control:data.control_available,releasePending:data.durable_release_pending});
  const disclosure=output.locator('details').filter({has:page.getByText('Open this session in a terminal',{exact:true})});
  await disclosure.locator('summary').click();const expected='okto-nexus work chat --session-id '+cfg.scope.session_id;
  check('exact-existing-session-command',await disclosure.locator('code').filter({hasText:expected}).count()===1,expected);
  const copy=disclosure.getByRole('button',{name:'Copy command',exact:true});check('Copy-command-present-enabled',await copy.isVisible()&&await copy.isEnabled(),{clipboard:'NOT_CLICKED: no proven browser-only clipboard isolation; Windows clipboard untouched'});
  await disclosure.locator('summary').click();await page.screenshot({path:cfg.output+'-terminal.png'});await modal.getByRole('button',{name:'Close modal',exact:true}).click();await modal.waitFor({state:'hidden'});
  check('zero-browser-POST',page.__overlayWrites.length===0,page.__overlayWrites);check('zero-page-errors',page.__overlayErrors.length===0,page.__overlayErrors);
  return {status:'PASS_OVERLAY_BROWSER_FOCAL',checks,limits:['Real Chrome + real installed R9 HTTP API + new Vite static-only overlay; not a new installed wheel','No clipboard click, provider or human acceptance']};
 }catch(e){return {status:'INCOMPLETE_OVERLAY_FOCAL',checks,error:String(e),writes:page.__overlayWrites??[],pageErrors:page.__overlayErrors??[],AX:await page.locator('body').ariaSnapshot().catch(()=>null)};}
}
