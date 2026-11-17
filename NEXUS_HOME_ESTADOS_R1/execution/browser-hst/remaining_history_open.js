async page=>{
 const cfg=__CONFIG__,checks=[],reads=[];if(cfg.window!=='REMAINING_FUNCTIONAL_WINDOW_OPEN')throw Error('Root review/window required');
 const check=(id,ok,detail)=>{checks.push({id,ok,detail});if(!ok)throw Error(id);};
 page.on('response',r=>{if(new URL(r.url()).pathname==='/api/v1/home/target')reads.push({status:r.status(),url:r.url()});});
 try{
  await page.addInitScript(({workspace})=>{localStorage.setItem('okto-nexus-home-operational','enabled');localStorage.setItem('okto-nexus-workspace',workspace);localStorage.setItem('okto-nexus:metrics-opt-in-prompt-dismissed:1.0.0',new Date().toISOString());},{workspace:cfg.workspace_id});
  await page.goto(cfg.url,{waitUntil:'domcontentloaded'});const signal=page.locator('[data-home-signal="'+cfg.delivery_id+'"]');await signal.waitFor({timeout:10000});
  await signal.getByRole('button',{name:'View result',exact:true}).click();await page.getByRole('dialog',{name:'Activity detail'}).waitFor({timeout:10000});
  const actual=JSON.parse(new URL(page.url()).searchParams.get('home_target'));
  check('canonical-delivery-opens-known-retained-session',Object.entries(cfg.target).every(([k,v])=>actual[k]===v)&&actual.session_id===cfg.session_id,{target:actual});
  return {status:'PASS_SUBSET',checks,reads,limits:['Two sessions; explicit older retained session through its canonical delivery, never latest']};
 }catch(error){return {status:'FAIL_OR_INCOMPLETE',error:String(error),checks,reads};}
}
