async (page) => {
  await page.context().addInitScript(() => {
    localStorage.setItem('okto-nexus-home-operational','enabled');
    localStorage.setItem('okto.nexus.onboarding.completed.v1','true');
    localStorage.setItem('okto-nexus:metrics-opt-in-prompt-dismissed:1.0.0','fixture-dismissed');
    localStorage.setItem('okto-nexus-workspace','home-alpha');
  });
  await page.route('**/api/**', async route => {
    if (!['GET','HEAD','OPTIONS'].includes(route.request().method()))
      return route.fulfill({status:405,contentType:'application/json',body:JSON.stringify({ok:false,error:{code:'FIXTURE_MUTATION_REFUSED',message:'Read-only browser fixture'}})});
    return route.continue();
  });
  await page.reload();
  await page.getByRole('heading',{name:'Review the integration',exact:true}).waitFor();
  return await page.locator('body').ariaSnapshot();
}
