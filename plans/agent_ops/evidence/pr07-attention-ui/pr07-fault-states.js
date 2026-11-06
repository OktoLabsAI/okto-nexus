async (page) => {
  const pattern = /\/api\/v1\/attention(?:\?|\/summary|$)/;
  const before = await page.locator('[data-attention-id]').count();
  if (before !== 2) throw new Error(`Expected delivery + verified result, got ${before}`);
  await page.route(pattern, route => route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({ok:false,error:{code:'DB_ERROR',message:'Synthetic read outage'}})}));
  await page.getByRole('button',{name:'Refresh attention',exact:true}).click();
  await page.getByText('Synthetic read outage', {exact:true}).waitFor();
  const stale = await page.locator('[data-attention-id]').count();
  if (stale !== before || await page.getByTestId('attention-empty').count()) throw new Error('Read failure erased or falsified the snapshot');
  await page.screenshot({path:'attention-read-outage.png'});
  await page.unroute(pattern);
  await page.route(pattern, route => route.fulfill({status:403,contentType:'application/json',body:JSON.stringify({ok:false,error:{code:'PERMISSION_DENIED',message:'Synthetic authorization revocation'}})}));
  await page.getByRole('button',{name:'Refresh attention',exact:true}).click();
  await page.getByRole('heading',{name:'Operator access required'}).waitFor();
  const forbidden = await page.locator('[data-attention-id]').count();
  const badges = await page.getByTestId('attention-badge').count();
  if (forbidden !== 0 || badges !== 0 || await page.getByTestId('attention-inspection').count()) throw new Error('Protected data remained');
  await page.screenshot({path:'attention-forbidden.png'});
  await page.unroute(pattern);
  await page.getByRole('button',{name:'Refresh attention',exact:true}).click();
  await page.getByRole('heading',{name:'Delivery needs attention',exact:true}).waitFor();
  return {injection:'Browser response faults; real backend unchanged',before,retainedOn503:stale,after403:forbidden,badgesAfter403:badges,recovered:true};
}
