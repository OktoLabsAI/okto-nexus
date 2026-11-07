async (page) => {
  const base = 'http://127.0.0.1:49707';
  const read = async () => {
    const response = await page.request.get(`${base}/api/v1/settings`);
    if (response.status() !== 200) throw new Error('Settings read failed');
    return Object.fromEntries((await response.json()).data.items.map(item => [item.key, item.value]));
  };
  const saved = await read();
  if (saved.feature_observations !== true || saved.observation_source_burst !== 21) throw new Error('UI save did not persist');
  const originalViewport = page.viewportSize();
  await page.reload();
  if (await page.getByRole('heading', {name:'Settings',exact:true}).count() === 0) {
    await page.getByTestId('header-menu').click();
    await page.getByRole('button', {name:'Settings',exact:true}).click();
  }
  await page.getByRole('tab', {name:'Observations',exact:true}).click();
  await page.getByRole('checkbox', {name:'Feature observations',exact:true}).waitFor();
  if (!await page.getByRole('checkbox', {name:'Feature observations',exact:true}).isChecked()) throw new Error('Toggle lost on reload');
  if (await page.getByRole('spinbutton', {name:'Observation source burst',exact:true}).inputValue() !== '21') throw new Error('Limit lost on reload');
  const panel = page.getByRole('tabpanel', {name:'Observations',exact:true});
  const controls = await panel.locator('input').count();
  if (controls !== 16) throw new Error(`Expected 16 controls, found ${controls}`);
  const ttl = page.getByRole('spinbutton', {name:/^Observation max valid for seconds(?: modified)?$/});
  await ttl.fill('0');
  if (!await page.getByTestId('save-settings').isDisabled()) throw new Error('Invalid TTL allowed save');
  await ttl.fill('3600');
  await page.getByRole('checkbox', {name:'Feature observations',exact:true}).uncheck();
  await page.getByRole('spinbutton', {name:'Observation source burst',exact:true}).fill('20');
  await page.getByTestId('save-settings').click();
  await page.getByText('All changes saved', {exact:true}).waitFor();
  const restored = await read();
  if (restored.feature_observations !== false || restored.observation_source_burst !== 20) throw new Error('Restore failed');
  const changedOther = Object.keys(saved).filter(key => !key.startsWith('observation_') && key !== 'feature_observations' && JSON.stringify(saved[key]) !== JSON.stringify(restored[key]));
  if (changedOther.length) throw new Error('Unrelated settings changed: ' + changedOther.join(','));
  await page.getByTestId('header-menu').click();
  await page.getByRole('button', {name:'Dark Mode',exact:true}).click();
  await page.screenshot({path:'output/playwright/pr08-observations-dark.png',fullPage:true});
  await page.setViewportSize({width:390,height:844});
  if (await page.getByRole('button', {name:'Collapse menu',exact:true}).count()) {
    await page.getByRole('button', {name:'Collapse menu',exact:true}).click();
  }
  const dimensions = await page.evaluate(() => ({viewport:innerWidth,document:document.documentElement.scrollWidth}));
  if (dimensions.document > dimensions.viewport) throw new Error('Horizontal document overflow: ' + JSON.stringify(dimensions));
  await page.screenshot({path:'output/playwright/pr08-observations-mobile-dark.png',fullPage:true});
  await page.setViewportSize(originalViewport);
  return {browser:page.context().browser().version(), controls, saved:{enabled:true,sourceBurst:21},
    reloadPreserved:true, invalidTtlDisablesSave:true, restored:{enabled:false,sourceBurst:20},
    unrelatedSettingsUnchanged:true, dimensions, screenshots:3};
}
