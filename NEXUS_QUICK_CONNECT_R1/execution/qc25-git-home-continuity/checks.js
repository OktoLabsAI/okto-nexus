async page => {
 const cfg={"root": "C:\\Users\\jpamb\\AppData\\Local\\Temp\\nexus-qc25-continuity-wi9joyyc", "fixture": "C:\\Users\\jpamb\\AppData\\Local\\Temp\\nexus-qc-git-cli-complete-3hnalsq1\\git-cli-composed\\tmp\\pytest-of-unknown\\pytest-0\\test_origin_first_connect_and_0", "home": "C:\\Users\\jpamb\\AppData\\Local\\Temp\\nexus-qc-git-cli-complete-3hnalsq1\\git-cli-composed\\tmp\\pytest-of-unknown\\pytest-0\\test_origin_first_connect_and_0\\home", "port": 63600, "url": "http://127.0.0.1:63600", "project_root": "C:\\Users\\jpamb\\AppData\\Local\\Temp\\nexus-qc-git-cli-complete-3hnalsq1\\git-cli-composed\\tmp\\pytest-of-unknown\\pytest-0\\test_origin_first_connect_and_0\\workspace", "logical_name": "logical-origin", "reference": {"agent_id": "logical-origin-8fa97a7587f4", "binding_id": "bind_8120aeebd683f8185deac2e8a37915dc", "endpoint_id": "ep_3a88cec4171e3351622e533e727389f8", "executor_id": "exe_e5d3beb45d6f3313bd795992e421098b", "server_id": "srv_8fd39ed3535a1679f5fd61207e3ff189", "workspace_binding_id": "wxb_1ce60854c5daa44a44dbb7f355db2069", "workspace_id": "wsr_20e617a81d8c3c6f8b39ad77f747dd67"}, "connect_id": "codex", "profile_sha256": "aa4e2228a79e6d770a0fc5e6a197fbfaef93a0340e1376c13c27a90a80665bc8", "original_process_marker_matches": [], "observed_at": "2026-11-17T08:48:27.599238+00:00"}, checks=[], requests=[], responses=[], pageErrors=[], consoleErrors=[];
 const check=(name,ok,data={})=>{checks.push({name,status:ok?'PASS':'FAIL',...data});if(!ok)throw Error(name);};
 page.on('request',r=>requests.push({method:r.method(),path:new URL(r.url()).pathname}));
 page.on('response',r=>{if(r.url().includes('/api/'))responses.push({status:r.status(),path:new URL(r.url()).pathname});});
 page.on('pageerror',e=>pageErrors.push(e.message));
 page.on('console',m=>{if(m.type()==='error')consoleErrors.push(m.text());});
 const get=async path=>{const r=await page.request.get(new URL(path,page.url()).href,{headers:{'X-Nexus-UI':'1'}});check('Real canonical GET '+path.split('?')[0],r.status()===200,{status:r.status()});const value=await r.json();return value.data??value;};
 try {
  const project=page.getByTestId('home-project-card');
  check('Old logical project stays selected',await project.getByRole('combobox',{name:'Project',exact:true}).inputValue()===cfg.reference.workspace_id&&await project.getByText(cfg.logical_name,{exact:true}).count()>=1);
  await page.getByRole('heading',{name:'Harness ID: '+cfg.connect_id,exact:true}).waitFor();
  const main=await page.getByRole('main').innerText();
  check('Same bound Harness ID visible after changed Git origin',main.includes('Harness ID: '+cfg.connect_id)&&main.includes(cfg.logical_name)&&!main.includes('different-name'),{main});
  const labels=await page.getByRole('list',{name:'Main destinations',exact:true}).getByRole('button').allTextContents();
  check('Basic navigation remains unchanged',JSON.stringify(labels)===JSON.stringify(['Home','Conversations','Graph','Artifacts']),{labels});
  const board=await get('/api/v1/home/harness-board?workspace_id='+encodeURIComponent(cfg.reference.workspace_id));
  const cards=Object.values(board.columns).flatMap(c=>c.items).filter(i=>i.kind==='harness');
  const card=cards.find(i=>i.connection.binding_id===cfg.reference.binding_id);
  const homeFields=['server_id','executor_id','workspace_id','binding_id','workspace_binding_id','agent_id'];
  check('Home card retains the original canonical connection',!!card&&card.connection.connect_id===cfg.connect_id&&homeFields.every(k=>card.connection[k]===cfg.reference[k]),{connection:card?.connection,board_status:board.status,source_status:board.source_status});
  const binding=await get('/api/v1/runtime-management/connections/bindings/'+encodeURIComponent(cfg.reference.binding_id));
  check('Binding GET retains all seven canonical fields',Object.entries(cfg.reference).every(([k,v])=>binding[k]===v),{reference:Object.fromEntries(Object.keys(cfg.reference).map(k=>[k,binding[k]])),state:binding.state});
  const resolved=await get('/api/v1/home/target?'+new URLSearchParams({target:JSON.stringify(card.target),workspace_id:cfg.reference.workspace_id}));
  check('Original connection target remains available',resolved.available===true&&homeFields.every(k=>resolved.connection_context[k]===cfg.reference[k]),{target:resolved.target,context:resolved.connection_context});
  await page.getByRole('heading',{name:'Project',exact:true}).scrollIntoViewIfNeeded();
  await page.screenshot({path:'output/playwright/qc25/desktop-home.png',fullPage:false});
  await page.getByRole('button',{name:'Inspect execution',exact:true}).click();
  await page.getByRole('dialog').waitFor();
  check('Inspect opens one passive context',await page.getByRole('dialog').count()===1,{dialog:await page.getByRole('dialog').innerText()});
  await page.screenshot({path:'output/playwright/qc25/connection-context.png',fullPage:false});
  check('No mutating requests or frontend errors during focused observation',requests.every(r=>['GET','HEAD','OPTIONS'].includes(r.method))&&pageErrors.length===0&&consoleErrors.length===0,{pageErrors,consoleErrors});
  return {status:'PASS',checks,requests,responses,pageErrors,consoleErrors};
 } catch(e) {
  await page.screenshot({path:'output/playwright/qc25/failure.png',fullPage:false});
  return {status:'FAIL',message:e.message,checks,requests,responses,pageErrors,consoleErrors};
 }
}
