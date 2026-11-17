async page => {
 const requests=[], blocked=[], pageErrors=[], consoleErrors=[];
 await page.route('**/*', async route => {
  const r=route.request();
  if(!['GET','HEAD','OPTIONS'].includes(r.method())) {blocked.push({method:r.method(),path:new URL(r.url()).pathname});return route.abort();}
  return route.continue();
 });
 page.on('request',r=>requests.push({method:r.method(),path:new URL(r.url()).pathname}));
 page.on('pageerror',e=>pageErrors.push(e.message));
 page.on('console',m=>{if(m.type()==='error')consoleErrors.push(m.text());});
 await page.addInitScript(()=>localStorage.setItem('okto-nexus-home-operational','enabled'));
 await page.setViewportSize({width:1440,height:1100});
 await page.goto('http://127.0.0.1:63600/',{waitUntil:'domcontentloaded'});
 await page.getByRole('heading',{name:'Project',exact:true}).waitFor({timeout:20000});
 return {status:'INITIALIZED',body:await page.locator('body').innerText(),requests,blocked,pageErrors,consoleErrors};
}
