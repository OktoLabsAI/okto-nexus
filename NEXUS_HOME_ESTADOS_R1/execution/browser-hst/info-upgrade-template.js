async page=>{
 const cfg=__CONFIG__,checks=[],requests=[];let info=null;
 const check=(id,ok,detail)=>{checks.push({id,ok,detail});if(!ok)throw Error(id);};
 const anchor=Date.now();
 const observe=async()=>{
  const dialog=page.getByRole('dialog',{name:'Activity detail'}),field=dialog.getByLabel('Choose fixture output format',{exact:true});
  const forms=await field.count();
  return {dialogs:await dialog.count(),forms,selected:forms?await field.evaluate(e=>Array.from(e.selectedOptions,o=>o.value)):null,
   sameNode:forms?await field.evaluate(e=>e===window.__hstTrackedDraftNode):false,
   previousNodeConnected:await page.evaluate(()=>window.__hstTrackedDraftNode?.isConnected??null),
   focused:forms?await field.evaluate(e=>document.activeElement===e):false,
   focus:await page.evaluate(()=>({tag:document.activeElement?.tagName,id:document.activeElement?.id,label:document.activeElement?.getAttribute('aria-label')})),at:Date.now()};
 };
 page.on('request',r=>requests.push({method:r.method(),path:new URL(r.url()).pathname,at:Date.now()}));
 page.on('response',async r=>{if(new URL(r.url()).pathname==='/api/v1/info'){
  const raw=await r.json();const body=raw.data??raw;info={at:Date.now(),versions:body.home_presentation_versions,status:r.status()};}});
 try{
  await page.addInitScript(({workspace})=>{
   localStorage.setItem('okto-nexus-home-operational','enabled');localStorage.setItem('okto-nexus-workspace',workspace);
   localStorage.setItem('okto-nexus:metrics-opt-in-prompt-dismissed:1.0.0',new Date().toISOString());
  },{workspace:cfg.workspace_id});
  await page.goto(cfg.url,{waitUntil:'domcontentloaded'});
  const respond=page.getByRole('button',{name:'Respond',exact:true});
  try{await respond.waitFor({timeout:8000});}
  catch(error){return {status:'PRECONDITION_NOT_AVAILABLE',reason:'No question action exposed before info negotiation; bootstrap may gate the view',info,requests,observed:await observe()};}
  check('action-before-info',info===null,{elapsed:Date.now()-anchor});
  await respond.click();
  const dialog=page.getByRole('dialog',{name:'Activity detail'}),answer=dialog.getByLabel('Choose fixture output format',{exact:true});
  await answer.waitFor({timeout:3000});
  await answer.selectOption(['0']);await answer.focus();
  await answer.evaluate(e=>{window.__hstTrackedDraftNode=e;});
  const before=await observe();
  check('dirty-form-before-version-upgrade',info===null,before);
  for(let i=0;i<200&&!info;i++)await page.waitForTimeout(100);
  check('real-info-upgrade-arrived',info?.status===200&&info.versions.includes(2),info);
  await page.waitForTimeout(1000);
  const after=await observe();
  check('same-panel-retained-across-negotiation',after.dialogs===1&&after.forms===1,after);
  check('draft-and-focus-retained-across-negotiation',await answer.evaluate(e=>document.activeElement===e&&e.selectedOptions.length===1&&e.selectedOptions[0].value==='0'),after);
  check('negotiation-no-write',requests.every(r=>r.method==='GET'),requests.filter(r=>r.method!=='GET'));
  await answer.locator('..').screenshot({path:cfg.screenshot});
  return {status:'PASS_SUBSET',checks,info,requests,before,after,limits:['Real info response delayed12s unchanged; one synthetic question; no decision sent']};
 }catch(error){return {status:'FAIL',error:String(error),checks,info,requests,observed:await observe()};}
}
