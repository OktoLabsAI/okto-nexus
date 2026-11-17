async page=>{
 const cfg={"url": "http://127.0.0.1:56524", "workspace_id": "wsr_271875c006b04a2472932b1505355571"};
 await page.addInitScript(({workspace})=>{
  localStorage.setItem('okto-nexus-home-operational','enabled');
  localStorage.setItem('okto-nexus-workspace',workspace);
  localStorage.setItem('okto-nexus:metrics-opt-in-prompt-dismissed:1.0.0',new Date().toISOString());
 },{workspace:cfg.workspace_id});
 await page.setViewportSize({width:1440,height:1100});
 await page.goto(cfg.url,{waitUntil:'domcontentloaded'});
 await page.getByTestId('home-board').waitFor({timeout:15000});
 return {url:page.url(),snapshot:await page.locator('body').ariaSnapshot()};
}
