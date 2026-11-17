async page=>{
  const target={kind:'approval',server_id:'srv_dc98adb0832234e4937534ea4baf9722',workspace_id:'ws',approval_id:'r4request_a08c152569b185cad37b01e036aad6ca7eaf21256c1543e874a0f2b12cb96c3e'};
  const posts=[];page.on('request',r=>{if(r.method()==='POST')posts.push(new URL(r.url()).pathname);});
  await page.goto('http://127.0.0.1:49699/?home_target='+encodeURIComponent(JSON.stringify(target)));
  await page.getByTestId('canonical-native-status').waitFor();
  const visible=await page.getByTestId('canonical-native-status').innerText();
  const pass=visible.includes('DISPATCH_PENDING')&&visible.includes('does not prove application by the provider')&&posts.length===0&&await page.getByRole('dialog').count()===1;
  await page.screenshot({path:'NEXUS_UI_R1/execution/evidence/pr07-panel09-lost-response/reopened.png',fullPage:true});
  return {status:pass?'PASS':'FAIL',target,visible,posts,dialogs:await page.getByRole('dialog').count()};
}
