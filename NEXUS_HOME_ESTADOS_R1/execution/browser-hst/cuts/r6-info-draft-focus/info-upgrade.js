async page=>{
 const cfg={"url": "http://127.0.0.1:53780", "workspace_id": "wsr_a60c91bc43434734557fa930e74097a9", "screenshot": "D:\\Projetos\\Techridy\\okto_labs_okto_nexus\\output\\playwright\\home-states\\r6-info-draft.png"},checks=[],requests=[],boards=[];let info=null;
 const check=(id,ok,detail)=>{checks.push({id,ok,detail});if(!ok)throw Error(id);};
 page.on('request',r=>requests.push({method:r.method(),path:new URL(r.url()).pathname,at:Date.now()}));
 page.on('response',async r=>{const u=new URL(r.url());
  if(u.pathname.includes('/home/harness-board'))boards.push({at:Date.now(),version:u.searchParams.get('presentation_version')??'1',status:r.status()});
  if(u.pathname==='/api/v1/info'){const raw=await r.json();info={at:Date.now(),versions:(raw.data??raw).home_presentation_versions,status:r.status()};}
 });
 try{
  await page.addInitScript(({workspace})=>{localStorage.setItem('okto-nexus-home-operational','enabled');localStorage.setItem('okto-nexus-workspace',workspace);localStorage.setItem('okto-nexus:metrics-opt-in-prompt-dismissed:1.0.0',new Date().toISOString());},{workspace:cfg.workspace_id});
  await page.goto(cfg.url,{waitUntil:'domcontentloaded'});
  const respond=page.getByRole('button',{name:'Respond',exact:true});await respond.waitFor({timeout:8000});
  check('action-before-info',info===null,true);await respond.click();
  const dialog=page.getByRole('dialog',{name:'Activity detail'}),answer=dialog.getByLabel('Choose fixture output format',{exact:true});
  await answer.waitFor({timeout:3000});await answer.selectOption(['0']);await answer.focus();
  await answer.evaluate(e=>{window.__hstTrackedDraftNode=e;});
  check('dirty-before-info',info===null,true);
  for(let i=0;i<200&&!info;i++)await page.waitForTimeout(100);
  check('info-actually-offers-v2',info?.status===200&&info.versions.includes(2),info);
  await page.waitForTimeout(800);
  const retained=await answer.evaluate(e=>({same:e===window.__hstTrackedDraftNode,connected:window.__hstTrackedDraftNode.isConnected,selected:Array.from(e.selectedOptions,o=>o.value),focused:document.activeElement===e}));
  check('same-node-draft-focus-retained',retained.same&&retained.connected&&retained.focused&&JSON.stringify(retained.selected)==='["0"]',retained);
  check('version-one-during-context',!boards.some(x=>x.version==='2'),boards);
  await answer.locator('..').screenshot({path:cfg.screenshot});
  await dialog.getByRole('button',{name:'Close modal',exact:true}).click();
  await page.getByRole('button',{name:'Discard changes',exact:true}).click();
  await dialog.waitFor({state:'hidden'});await page.waitForTimeout(300);
  const focus=await page.evaluate(()=>({inBoard:!!document.activeElement?.closest('[data-home-harness],[data-home-entry],[data-home-signal]'),tag:document.activeElement?.tagName,label:document.activeElement?.textContent}));
  check('close-restores-board-focus',focus.inBoard,focus);
  check('version-one-until-board-blur',!boards.some(x=>x.version==='2'),boards);
  await page.getByRole('heading',{name:'Home',exact:true}).evaluate(e=>{e.setAttribute('tabindex','-1');e.focus();});
  for(let i=0;i<100&&!boards.some(x=>x.version==='2'&&x.status===200);i++)await page.waitForTimeout(100);
  check('blur-adopts-v2',boards.some(x=>x.version==='2'&&x.status===200),boards);
  check('no-write',requests.every(r=>r.method==='GET'),requests.filter(r=>r.method!=='GET'));
  return {status:'PASS_SUBSET',checks,info,boards,requests,limits:['Delayed unchanged real info response; own synthetic operator question; explicit discard, no decision']};
 }catch(error){return {status:'FAIL',error:String(error),checks,info,boards,requests,focus:await page.evaluate(()=>({tag:document.activeElement?.tagName,label:document.activeElement?.getAttribute('aria-label')}))};}
}
