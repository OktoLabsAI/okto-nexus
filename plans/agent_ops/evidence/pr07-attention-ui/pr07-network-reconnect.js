async (page) => {
  const ids = await page.locator('[data-attention-id]').evaluateAll(rows => rows.map(row=>row.dataset.attentionId).sort());
  await page.context().setOffline(true);
  await page.getByRole('button',{name:'Refresh attention',exact:true}).click();
  await page.getByText('Failed to fetch',{exact:true}).waitFor({timeout:20000});
  const offline = await page.locator('[data-attention-id]').evaluateAll(rows=>rows.map(row=>row.dataset.attentionId).sort());
  if (JSON.stringify(ids)!==JSON.stringify(offline)) throw new Error('Offline refresh changed episodes');
  await page.context().setOffline(false);
  await page.getByRole('button',{name:'Refresh attention',exact:true}).click();
  await page.getByText('Failed to fetch',{exact:true}).waitFor({state:'hidden',timeout:20000});
  await page.waitForFunction(()=>document.querySelector('[data-testid="attention-page-count"]')?.textContent.includes('Live updates'));
  const connected = await page.locator('[data-attention-id]').evaluateAll(rows=>rows.map(row=>row.dataset.attentionId).sort());
  if (JSON.stringify(ids)!==JSON.stringify(connected)) throw new Error('Reconnect replaced episodes');
  return {case:'real browser network offline/online',before:ids,offline,connected,live:true};
}
