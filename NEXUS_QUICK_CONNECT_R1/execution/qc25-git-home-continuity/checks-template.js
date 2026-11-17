async page => {
 const cfg=__CFG__, checks=[], requests=[], responses=[], pageErrors=[], consoleErrors=[];
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
