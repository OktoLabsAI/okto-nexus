async page=>{
  await page.addInitScript(()=>{localStorage.setItem('okto-nexus-home-operational','enabled');localStorage.setItem('okto-nexus-workspace','ws');localStorage.setItem('okto.nexus.onboarding.completed.v1','true');localStorage.setItem('okto-nexus:metrics-opt-in-prompt-dismissed:1.0.0','test');});
  await page.goto('http://127.0.0.1:51859');
  await page.getByTestId('navigation-sidebar').getByRole('button',{name:'Graph',exact:true}).click();
  return {view:await page.getByRole('navigation',{name:'Breadcrumb'}).innerText(),bell:await page.getByTestId('global-attention-button').getAttribute('aria-label')};
}
