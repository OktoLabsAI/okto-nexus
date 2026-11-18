// PREPARED ONLY: substitute __CONFIG__ with public IDs/origin after Root gate.
// Official own human operator cookie is loaded separately from PRIVATE storage.
async (page) => {
  const cfg = __CONFIG__;
  const writes = [];
  page.on('request', request => {
    if (!['GET','HEAD','OPTIONS'].includes(request.method()))
      writes.push({method:request.method(),path:new URL(request.url()).pathname});
  });
  await page.context().setExtraHTTPHeaders({'X-Nexus-UI':'1','X-Nexus-Operator-Session-Required':'1'});
  await page.setViewportSize({width:1440,height:1000});
  await page.goto(cfg.origin);
  await page.getByRole('button',{name:'Home',exact:true}).click();
  await page.getByRole('combobox',{name:'Project',exact:true}).selectOption(cfg.workspace_id);
  if (await page.evaluate(()=>localStorage.getItem('okto-nexus-home-operational')) === 'enabled')
    throw new Error('Fresh own browser must start with the shipped classic default');
  await page.getByRole('heading',{name:'Harness sessions',exact:true}).waitFor();
  const settings = async () => {
    await page.getByRole('button',{name:'Advanced',exact:true}).click();
    await page.getByText('Settings',{exact:true}).click();
    await page.getByTestId('home-display-preference').waitFor();
  };
  await settings();
  await page.getByRole('button',{name:'Use operational Home',exact:true}).click();
  await page.getByRole('button',{name:'Home',exact:true}).click();
  await page.getByTestId('home-board').waitFor();
  if (await page.locator('[data-home-column]').count() !== 3)
    throw new Error('Operational Home did not expose all three columns');
  const response = await page.request.get(cfg.origin+'/api/v1/home/harness-board?presentation_version=2&workspace_id='+encodeURIComponent(cfg.workspace_id));
  if (response.status() !== 200) throw new Error('Canonical Home projection unavailable');
  const value = await response.json();
  const board = value.data ?? value;
  const cards = Object.values(board.columns).flatMap(column=>column.items).filter(item=>item.kind==='harness');
  const card = cards.find(item=>item.connection.binding_id===cfg.binding_id);
  if (!card || card.connection.workspace_id!==cfg.workspace_id) throw new Error('Exact CLI connection missing');
  await settings();
  await page.getByRole('button',{name:'Use classic Home',exact:true}).click();
  await page.getByRole('button',{name:'Home',exact:true}).click();
  await page.getByRole('heading',{name:'Harness sessions',exact:true}).waitFor();
  if (await page.getByTestId('home-board').count() !== 0) throw new Error('Rollback did not restore classic Home');
  if (await page.getByRole('combobox',{name:'Project',exact:true}).inputValue()!==cfg.workspace_id)
    throw new Error('Rollback changed the selected project');
  await page.getByTestId('global-attention-button').click();
  await page.getByTestId('attention-open-'+cfg.attention_id).waitFor();
  if (writes.length) throw new Error('Presentation rollback made non-read requests: '+JSON.stringify(writes));
  return {classic_default:true,settings_enable:true,operational_exact_binding:true,settings_rollback:true,
    classic_conversations:true,exact_global_question:true,selected_project_preserved:true,productive_posts:0,
    limits:'Browser UI only; PID/birth/generation/config/grant/checkpoint invariants require paired external snapshots.'};
}
