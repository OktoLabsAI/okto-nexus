async (page) => {
  const base = 'http://127.0.0.1:49262';
  const headers = {'x-nexus-ui':'1',Origin:base};
  if (await page.getByTestId('attention-inspection').count() !== 1) throw new Error('Expected open original-record inspection');
  const off = await page.request.patch(`${base}/api/v1/settings`,{headers,data:{feature_attention:false}});
  if (off.status() !== 200) throw new Error(`Feature toggle failed: ${off.status()}`);
  await page.getByRole('heading',{name:'Attention is disabled',exact:true}).waitFor({timeout:20000});
  const cleared = {cards:await page.locator('[data-attention-id]').count(),badge:await page.getByTestId('attention-badge').count(),inspection:await page.getByTestId('attention-inspection').count()};
  if (Object.values(cleared).some(Boolean)) throw new Error(JSON.stringify(cleared));
  await page.screenshot({path:'attention-feature-off.png'});
  const on = await page.request.patch(`${base}/api/v1/settings`,{headers,data:{feature_attention:true}});
  if (on.status() !== 200) throw new Error(`Restore failed: ${on.status()}`);
  await page.getByRole('button',{name:'Refresh attention',exact:true}).click();
  await page.getByRole('heading',{name:'Delivery needs attention',exact:true}).waitFor();
  return {case:'real feature toggle with canonical settings API',offStatus:off.status(),cleared,onStatus:on.status(),recovered:true};
}
