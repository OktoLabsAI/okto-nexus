async page => {
  const origin=new URL(page.url()).origin;
  await page.context().setExtraHTTPHeaders({});
  const identity=await(await page.request.get(origin+'/__fixture_test_identity')).json();
  await page.context().setExtraHTTPHeaders({Authorization:'Bearer '+identity.key});
  await page.clock.setFixedTime(new Date(identity.frozen_time));
  await page.context().addInitScript(()=>{
    localStorage.setItem('okto-nexus-home-operational','enabled');
    localStorage.setItem('okto.nexus.onboarding.completed.v1','true');
    localStorage.setItem('okto-nexus:metrics-opt-in-prompt-dismissed:1.0.0','test');
  });
  await page.reload();
  await page.getByRole('region',{name:'Work',exact:true}).waitFor();
  return {ready:true,synthetic:true};
}
