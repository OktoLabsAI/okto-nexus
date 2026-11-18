// Public Chrome Settings UI only; app modal must already be closed.
async page=>{
  const cfg=__CONFIG__;if(cfg.window!=='ROOT_I01_NATIVE_APP_OPEN')throw Error('I01 gate required');
  if(await page.locator('dialog[open]').count())throw Error('Do not navigate away from an open context');
  await page.goto('chrome://settings/appearance');
  const select=page.getByRole('combobox',{name:/^(Page zoom|Zoom da página):?$/i});await select.waitFor({timeout:12000});
  if(await select.evaluate(e=>e.tagName)!=='SELECT')throw Error('Unsupported native WebUI control');
  const options=await select.locator('option').evaluateAll(nodes=>nodes.map(n=>({value:n.value,label:n.label})));
  const match=options.filter(n=>n.label.replace(/\s/g,'')==='100%');if(match.length!==1)throw Error('Actual native100 option not observed');
  await select.selectOption({value:match[0].value});const actual=await select.evaluate(e=>e.selectedOptions[0].label);
  if(actual.replace(/\s/g,'')!=='100%')throw Error('Native100 UI did not confirm');
  return {status:'PASS_NATIVE_UI100_SELECTED',selected:actual,ariaSnapshot:await select.ariaSnapshot(),options,scope:'Native UI selection only; app geometry is checked separately'};
}
