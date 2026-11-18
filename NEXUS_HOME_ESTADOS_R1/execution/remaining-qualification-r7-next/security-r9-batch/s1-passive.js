async page => {
  // Use with playwright-cli run-code, after own storage-state load and snapshot.
  // __CONFIG__ is substituted only in an own Temp copy, never in this source.
  const cfg = __CONFIG__, checks = [], network = [], consoleErrors = [];
  const check = (id, ok, detail) => {
    checks.push({id, ok, detail});
    if (!ok) throw Error(id);
  };
  page.on('request', r => network.push({method:r.method(), path:new URL(r.url()).pathname}));
  page.on('pageerror', error => consoleErrors.push(String(error)));
  try {
    check('own-loopback-origin', /^http:\/\/127\.0\.0\.1:\d+$/.test(cfg.url), cfg.url);
    await page.addInitScript(({workspace}) => {
      localStorage.setItem('okto-nexus-home-operational', 'enabled');
      localStorage.setItem('okto-nexus-workspace', workspace);
      localStorage.setItem('okto-nexus:metrics-opt-in-prompt-dismissed:1.0.0', new Date().toISOString());
    }, {workspace:cfg.reference.workspace_id});
    await page.goto(cfg.url);
    await page.locator('[data-home-column="active"]').waitFor({timeout:15000});
    const response = await page.request.get(cfg.url + '/api/v1/home/harness-board?presentation_version=2&workspace_id=' + encodeURIComponent(cfg.reference.workspace_id));
    check('board-http-200', response.status() === 200, response.status());
    const raw = await response.json(), board = raw.data ?? raw;
    const cards = Object.values(board.columns).flatMap(lane => lane.items).filter(item => item.kind === 'harness');
    const matching = cards.filter(item => ['server_id','executor_id','binding_id','agent_id','workspace_id','workspace_binding_id'].every(key => item.connection?.[key] === cfg.reference[key]));
    check('one-exact-registered-card', matching.length === 1, matching.map(item => item.id));
    check('no-invented-reconnect', matching[0].reconnect_available === false, matching[0].reconnect_available ?? null);
    // Exact card ID avoids a first-card/latest-session heuristic.
    const card = page.locator('[data-home-harness=' + JSON.stringify(matching[0].id) + ']');
    await card.getByRole('button', {name:'Follow activity', exact:true}).click();
    const dialog = page.getByRole('dialog', {name:'Activity detail'});
    await dialog.waitFor({timeout:10000});
    check('exact-card-expansion-one-panel', await page.getByRole('dialog').count() === 1, matching[0].id);
    await dialog.getByRole('button', {name:'Close modal', exact:true}).click();
    await dialog.waitFor({state:'hidden'});
    const deliveries = board.columns.results.items.filter(item => item.kind === 'delivery' &&
      item.result?.detail_target?.session_id === cfg.closed_session_id);
    check('one-exact-retained-delivery', deliveries.length === 1, deliveries.map(item => item.id));
    const delivery = page.locator('[data-home-signal=' + JSON.stringify(deliveries[0].id) + ']');
    await delivery.getByRole('button', {name:'View result', exact:true}).click();
    await dialog.waitFor({timeout:10000});
    check('result-open-one-panel', await page.getByRole('dialog').count() === 1, deliveries[0].result.detail_target);
    await dialog.getByRole('button', {name:'Close modal', exact:true}).click();
    await dialog.waitFor({state:'hidden'});
    check('passive-network', network.every(item => ['GET','HEAD','OPTIONS'].includes(item.method)), network);
    check('no-page-errors', consoleErrors.length === 0, consoleErrors);
    return {status:'PASS_API_AND_HOME_SUBSET', checks, network,
      exact_card_id:matching[0].id,
      limits:['No forged URL, hostile DOM, decision denial or revoke-browser assertion in this increment',
        'Network checks alone do not prove database passivity; require paired fixture snapshots']};
  } catch (error) {
    return {status:'FAIL', error:String(error), checks, network, consoleErrors};
  }
}
