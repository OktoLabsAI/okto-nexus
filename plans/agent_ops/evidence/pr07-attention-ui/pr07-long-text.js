async (page) => {
  const pattern = /\/api\/v1\/attention(?:\?|$)/;
  const text = '<img src=x onerror="window.__attention_html_executed=true">' + 'LongExternalReference'.repeat(20);
  await page.route(pattern, async route => {
    const response = await route.fetch();
    const body = await response.json();
    if (body.data?.items?.length) {body.data.items[0].source_id=text;body.data.items[0].agent_id=text;}
    await route.fulfill({response,json:body});
  });
  await page.getByRole('button',{name:'Refresh attention',exact:true}).click();
  const reference = page.getByTestId('attention-source-reference').first();
  await reference.getByText(text,{exact:true}).waitFor();
  await reference.scrollIntoViewIfNeeded();
  const result = await page.evaluate(expected => ({textLiteral:document.querySelector('[data-testid="attention-source-reference"]').textContent===expected,
    imageElements:document.querySelectorAll('[data-attention-id] img').length, executed:window.__attention_html_executed===true,
    viewport:innerWidth,documentWidth:document.documentElement.scrollWidth,mainWidth:document.querySelector('main').clientWidth,
    mainScrollWidth:document.querySelector('main').scrollWidth}),text);
  if (!result.textLiteral || result.imageElements || result.executed || result.mainScrollWidth > result.mainWidth) throw new Error(JSON.stringify(result));
  await page.screenshot({path:'attention-long-text-mobile-dark.png'});
  await page.unroute(pattern);
  return {injection:'Render-only browser response; no canonical mutation',...result};
}
