async page=>{
 const cfg=__CFG__;
 await page.route('**/*',route=>['GET','HEAD','OPTIONS'].includes(route.request().method())?route.continue():route.abort());
 await page.addInitScript(()=>localStorage.setItem('okto-nexus-home-operational','enabled'));
 await page.setViewportSize({width:1440,height:1100});
 await page.goto(cfg.url,{waitUntil:'domcontentloaded'});
 await page.getByTestId('home-project-card').waitFor({timeout:15000});
 return {body:await page.locator('body').innerText()};
}
