async page=>{
 const cfg=__CFG__,checks=[],requests=[],responses=[],pageErrors=[],consoleErrors=[];
 page.setDefaultTimeout(15000);page.on('request',r=>requests.push({method:r.method(),url:r.url()}));
 page.on('response',r=>{if(r.url().includes('/api/'))responses.push({status:r.status(),url:r.url()});});
 page.on('pageerror',e=>pageErrors.push(e.message));page.on('console',m=>{if(m.type()==='error')consoleErrors.push(m.text());});
 const check=(name,ok,data={})=>{checks.push({name,status:ok?'PASS':'FAIL',...data});if(!ok)throw Error(name);};
 const get=async path=>{const r=await page.request.get(new URL(path,page.url()).href);check('GET '+path,r.status()===200);return r.json();};
 try{
  const expected=cfg.ids.find(i=>i.connect_id==='builder').canonical_ref;
  const dialog=page.getByRole('dialog',{name:'Connection context',exact:true});await dialog.waitFor();
  const text=await dialog.innerText();
  check('Already opened builder context displays its exact saved binding scope',text.includes(expected.binding_id)&&text.includes(expected.executor_id)&&text.includes(expected.workspace_binding_id)&&text.includes(expected.workspace_id)&&text.includes(expected.agent_id),{text,limit:'Read-only Connection context is a distinct dialog, not the Home entry testid. No repeated Open click.'});
  const binding=await get('/api/v1/runtime-management/connections/bindings/'+encodeURIComponent(expected.binding_id));
  check('Saved inspector resolves the complete seven-field identity',Object.entries(expected).every(([k,v])=>binding[k]===v),{canonical_ref:Object.fromEntries(Object.keys(expected).map(k=>[k,binding[k]]))});
  await page.screenshot({path:cfg.out+'/builder-exact-context.png',fullPage:false});
  await dialog.getByRole('button',{name:'Close modal',exact:true}).click();
  await page.getByRole('list',{name:'Main destinations',exact:true}).getByRole('button',{name:'Home',exact:true}).click();
  await page.getByRole('region',{name:'Needs you',exact:true}).getByRole('heading',{name:'Harness ID: reviewer',exact:true}).waitFor();
  const labels=await page.getByRole('list',{name:'Main destinations',exact:true}).getByRole('button').allTextContents();
  check('Basic navigation stays exactly Home Conversations Graph Artifacts',JSON.stringify(labels)===JSON.stringify(['Home','Conversations','Graph','Artifacts']),{labels});
  const board=(await get('/api/v1/home/harness-board?workspace_id=ws')).data;
  const active=board.columns.active.items,needs=board.columns.needs_you.items,results=board.columns.results.items;
  check('Same IDs and canonical context survive across Active Needs you and Results',active.some(i=>i.connection?.connect_id==='builder'&&i.connection.binding_id===expected.binding_id)&&active.some(i=>i.connection?.binding_id===cfg.legacy_binding&&i.connection.connect_id===null)&&needs.some(i=>i.connection?.connect_id==='reviewer'&&i.connection.binding_id===cfg.ids.find(i=>i.connect_id==='reviewer').canonical_ref.binding_id)&&results.some(i=>i.harness_refs.some(r=>r.connection.connect_id==='builder'&&r.connection.binding_id===expected.binding_id)),{active:active.map(i=>({id:i.id,kind:i.kind,connection:i.connection})),needs:needs.map(i=>({id:i.id,kind:i.kind,connection:i.connection})),results:results.map(i=>({id:i.id,kind:i.kind,harness_refs:i.harness_refs,target:i.target,result:i.result?{id:i.result.id,target:i.result.target}:null}))});
  check('DOM headings retain public IDs plus explicit legacy fallback',await page.getByRole('region',{name:'Active',exact:true}).getByRole('heading',{name:'Harness ID: builder',exact:true}).count()===1&&await page.getByRole('region',{name:'Needs you',exact:true}).getByRole('heading',{name:'Harness ID: reviewer',exact:true}).count()===1&&await page.getByText('Harness ID not assigned',{exact:true}).count()===1);
  await page.setViewportSize({width:1440,height:1000});await page.screenshot({path:cfg.out+'/home-desktop.png',fullPage:false});
  await page.getByRole('region',{name:'Results',exact:true}).getByRole('button',{name:'View delivery',exact:true}).click();
  await page.getByRole('dialog').waitFor();
  await page.screenshot({path:cfg.out+'/delivery-context.png',fullPage:false});
  check('Delivery click opens one explicit contextual dialog',await page.getByRole('dialog').count()===1,{dialog:await page.getByRole('dialog').innerText(),url:page.url()});
  check('No writes or frontend errors while opening exact contexts',requests.every(r=>r.method==='GET')&&pageErrors.length===0&&consoleErrors.length===0&&responses.every(r=>r.status<400),{pageErrors,consoleErrors});
  return{status:'PASS',checks,requests,responses,pageErrors,consoleErrors};
 }catch(e){await page.screenshot({path:cfg.out+'/continuation-failure.png',fullPage:false});return{status:'FAIL',message:e.message,checks,requests,responses,pageErrors,consoleErrors};}
}
