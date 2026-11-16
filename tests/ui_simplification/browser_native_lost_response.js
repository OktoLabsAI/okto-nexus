async page=>{
  const cfg=__FIXTURE_CONFIG__,checks=[],posts=[];
  page.setDefaultTimeout(10000);
  await page.addInitScript(()=>{
    localStorage.setItem('okto-nexus-home-operational','enabled');
    localStorage.setItem('okto-nexus-workspace','ws');
    localStorage.setItem('okto.nexus.onboarding.completed.v1','true');
    localStorage.setItem('okto-nexus:metrics-opt-in-prompt-dismissed:1.0.0','test');
  });
  let accepted;
  await page.route('**/runtime/approval-decisions',async route=>{
    if(route.request().method()!=='POST')return route.continue();
    posts.push({path:new URL(route.request().url()).pathname});
    if(posts.length!==1){await route.abort();throw Error('Second productive POST refused');}
    // The actual handler commits first. Only its successful HTTP response is
    // dropped; no request or canonical DTO is mocked or changed.
    const response=await route.fetch();
    accepted={status:response.status(),body:await response.json()};
    if(accepted.status!==202){await route.fulfill({response});return;}
    await route.abort('connectionfailed');
  });
  await page.goto(cfg.url);await page.getByTestId('home-follow-up').waitFor();
  const expands=page.getByTestId('home-follow-up').getByRole('button',{name:'Expand',exact:true});
  while(await expands.count())await expands.first().click();
  await page.getByRole('button',{name:/^Open (question|approval)$/}).first().click();
  const dialog=page.getByTestId('home-detail'),form=page.getByTestId('native-approval-input');
  await form.locator('form').waitFor();await form.getByRole('listbox').selectOption('0');
  const scopeText=await dialog.getByRole('region',{name:'Native runtime decision'}).count().catch(()=>0);
  await page.getByRole('button',{name:'Send answer',exact:true}).click();
  await page.waitForFunction(()=>document.body.innerText.includes('A decision request was sent.'));
  await page.getByRole('button',{name:'Check native decision',exact:true}).click();
  await page.getByTestId('canonical-native-status').waitFor();
  if(!accepted||accepted.status!==202||accepted.body.native_stage!=='DISPATCH_PENDING')throw Error('Actual canonical202 missing');
  const visible=await page.getByTestId('canonical-native-status').innerText();
  if(!visible.includes('DISPATCH_PENDING')||!visible.includes('does not prove application by the provider'))throw Error('Recovery state mislabeled');
  checks.push({name:'Lost202 recovered by canonical read',status:'PASS',decision_id:accepted.body.decision_id,
    operation_id:accepted.body.native_operation_id,native_stage:accepted.body.native_stage});
  const approval=accepted.body.approval_key.canonical_request_id;
  await dialog.getByRole('button',{name:'Close modal',exact:true}).click();
  // Reopen the same exact question via the existing Attention target URL.
  // Refreshing detail in the existing Home panel recovers by persisted decision;
  // never send a second answer to discover whether the first was recorded.
  await page.reload();await page.getByTestId('home-follow-up').waitFor();
  // Use the canonical API to confirm same question after reload, not a latest lookup.
  const detail=await page.request.get(cfg.url+'/api/v1/approvals/'+encodeURIComponent(approval));
  if(detail.status()!==200)throw Error('Exact persisted question unavailable');
  const value=await detail.json(),result=(value.data??value).executed_result;
  if(result?.decision_id!==accepted.body.decision_id)throw Error('Different persisted decision');
  if(posts.length!==1)throw Error('Decision replayed');
  checks.push({name:'Same question persisted after reload; no second POST',status:'PASS',approval_id:approval});
  return {status:'PASS_SCOPED',checks,posts,accepted,scopeText,
    limits:['Canonical decision only; no native application','Reload exact question API read; UI reopened recovery qualified before reload']};
}
