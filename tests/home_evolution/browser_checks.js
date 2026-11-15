// Playwright MCP browser_run_code_unsafe function, no additional npm dependency.
// Requires the isolated, read-only browser_fixture.py and an opted-in Home tab.
async (page) => {
  const results = [];
  const mutations = [];
  const errors = [];
  const onRequest = request => {
    if (new URL(request.url()).origin === new URL(page.url()).origin &&
        !['GET', 'HEAD', 'OPTIONS'].includes(request.method()))
      mutations.push({method: request.method(), path: new URL(request.url()).pathname});
  };
  const onError = error => errors.push(error.message);
  page.on('request', onRequest);
  page.on('pageerror', onError);
  const assert = (condition, message) => { if (!condition) throw new Error(message); };
  const run = async (name, action) => {
    try { results.push({name, status: 'PASS', detail: await action()}); }
    catch (error) { results.push({name, status: 'FAIL', error: error.message}); throw error; }
  };
  const work = () => page.getByRole('region', {name: 'Work', exact: true});
  const waitOverview = () => page.waitForResponse(response =>
    response.url().includes('/api/v1/home/overview') && response.status() === 200);
  const refresh = async () => {
    const response = waitOverview();
    await page.evaluate(() => window.dispatchEvent(new Event('focus')));
    await response;
  };
  const selectScope = async value => {
    const response = waitOverview();
    await page.getByRole('combobox', {name: 'Workspace scope'}).selectOption(value);
    await response;
    await work().waitFor();
  };
  try {
    await page.setViewportSize({width: 1440, height: 1000});
    await run('Workspace filtering uses real GET projection and excludes global-only agents', async () => {
      await selectScope('home-beta');
      await work().getByRole('heading', {name: 'Lyra: independent request', exact: true}).waitFor();
      assert(await work().getByRole('heading', {name: 'Review the integration', exact: true}).count() === 0,
             'Orion activity leaked into Lyra');
      await selectScope('home-alpha');
      await work().getByRole('heading', {name: 'Review the integration', exact: true}).waitFor();
      assert(await work().getByRole('heading', {name: 'Lyra: independent request', exact: true}).count() === 0,
             'Lyra activity leaked into Orion');
      const agents = await page.getByRole('region', {name: 'Agents', exact: true}).innerText();
      assert(!agents.includes('global'), 'Unrelated global agent appears in a selected project');
      return {alphaHasReview: true, betaHasIndependentRequest: true, globalExcluded: true};
    });
    await run('Closing drawer after refresh preserves unchanged-revision pages and actual scroll container', async () => {
      const response = page.waitForResponse(value => value.url().includes('/api/v1/home/work?') && value.status() === 200);
      await page.getByRole('button', {name:'Load more work', exact:true}).click();
      await response;
      await page.waitForFunction(() => document.querySelector('[aria-label="Work"]').querySelectorAll('[data-home-item]').length === 15);
      const trigger = page.getByRole('button', {name:'Inspect Review batch item 12', exact:true});
      await trigger.scrollIntoViewIfNeeded();
      const before = await page.locator('[data-testid="operational-home"]').evaluate(element => element.parentElement.scrollTop);
      await trigger.click();
      await page.getByRole('dialog').getByRole('heading', {name:'browser-handoff-16', exact:true}).waitFor();
      await refresh();
      await page.keyboard.press('Escape');
      await page.getByRole('dialog').waitFor({state:'detached'});
      const count = await work().locator('[data-home-item]').count();
      const after = await page.locator('[data-testid="operational-home"]').evaluate(element => element.parentElement.scrollTop);
      assert(count === 15, 'Closing drawer discarded loaded pages');
      assert(Math.abs(before-after) <= 1, 'Closing drawer changed actual scroll position');
      assert(await trigger.evaluate(element => document.activeElement === element), 'Loaded-page trigger focus not restored');
      return {loadedActivities:count, scrollBefore:before, scrollAfter:after, focusRestored:true};
    });
    await run('Exact handoff drawer and keyboard close restore the trigger', async () => {
      const trigger = page.getByRole('button', {name: 'Inspect Review the integration', exact: true});
      await trigger.click();
      const dialog = page.getByRole('dialog', {name: 'Activity detail', exact: true});
      await dialog.getByRole('heading', {name: 'browser-handoff-0', exact: true}).waitFor();
      const target = JSON.parse(new URL(page.url()).searchParams.get('home_target'));
      assert(target.kind === 'handoff' && target.handoff_id === 'browser-handoff-0' &&
             target.workspace_id === 'home-alpha', 'Wrong canonical target');
      await page.keyboard.press('Escape');
      await dialog.waitFor({state: 'detached'});
      assert(await trigger.evaluate(element => document.activeElement === element), 'Focus not restored');
      return {kind: target.kind, handoff_id: target.handoff_id, focusRestored: true};
    });
    await run('Draft, focus and selection survive actual overview response; discard is explicit', async () => {
      await page.getByRole('button', {name: 'New request', exact: true}).click();
      const box = page.getByRole('textbox', {name: 'Message', exact: true});
      await box.fill('Synthetic draft retained across an actual GET.');
      await box.focus();
      await box.evaluate(element => {element.dataset.homeProbe='stable'; element.setSelectionRange(8,13);});
      await refresh();
      const retained = await box.evaluate(element => ({value:element.value,
        sameNode:element.dataset.homeProbe === 'stable', focused:document.activeElement === element,
        selection:[element.selectionStart,element.selectionEnd]}));
      assert(retained.sameNode && retained.focused && retained.selection.join(',') === '8,13', 'Draft focus/selection changed');
      assert(retained.value === 'Synthetic draft retained across an actual GET.', 'Draft changed');
      await page.keyboard.press('Escape');
      await page.getByText('Discard unsaved changes?', {exact:true}).waitFor();
      await page.getByRole('button', {name:'Keep editing', exact:true}).click();
      assert(await box.inputValue() === retained.value, 'Keep editing lost draft');
      await page.keyboard.press('Escape');
      await page.getByRole('button', {name:'Discard changes', exact:true}).click();
      return {sameNode:true, focusRetained:true, selectionRetained:true, discardGuard:true};
    });
    await run('360px document and exact-record drawer remain within viewport', async () => {
      await page.setViewportSize({width:360,height:800});
      const dimensions = await page.evaluate(() => ({viewport:innerWidth, document:document.documentElement.scrollWidth}));
      assert(dimensions.document <= dimensions.viewport, 'Page overflows horizontally');
      await page.getByRole('button', {name:'Inspect Review the integration', exact:true}).click();
      await page.getByRole('dialog').getByRole('heading', {name:'browser-handoff-0', exact:true}).waitFor();
      const drawer = await page.getByRole('dialog').evaluate(element => ({width:element.scrollWidth, viewport:innerWidth}));
      assert(drawer.width <= drawer.viewport, 'Drawer overflows horizontally');
      await page.keyboard.press('Escape');
      return {page:dimensions, drawer};
    });
    await run('Classic fallback is independent of work and still renders', async () => {
      await page.setViewportSize({width:1440,height:1000});
      await page.getByRole('button', {name:'Use classic Home', exact:true}).click();
      assert(await page.locator('[data-testid="operational-home"]').count() === 0, 'Operational view did not unmount');
      await page.getByRole('button', {name:'Use operational Home', exact:true}).click();
      await work().getByRole('heading', {name:'Review the integration', exact:true}).waitFor();
      return {classicRendered:true, operationalRestored:true, mutationRequests:mutations.length};
    });
    await run('A real 403 clears protected Home list and an open drawer', async () => {
      await page.getByRole('button', {name:'Inspect Review the integration', exact:true}).click();
      await page.getByRole('dialog').getByRole('heading', {name:'browser-handoff-0', exact:true}).waitFor();
      await page.route('**/api/v1/home/overview?*', route => route.fulfill({status:403,
        contentType:'application/json', body:JSON.stringify({ok:false,error:{code:'PERMISSION_DENIED',message:'Synthetic access revocation'}})}));
      const refused = page.waitForResponse(response => response.url().includes('/api/v1/home/overview') && response.status() === 403);
      await page.evaluate(() => window.dispatchEvent(new Event('focus')));
      await refused;
      await page.getByText('Operator access is required. Protected Home data has been cleared.', {exact:true}).waitFor();
      assert(await page.getByRole('dialog').count() === 0, 'Protected drawer survived 403');
      assert(await page.getByRole('heading', {name:'Review the integration', exact:true}).count() === 0,
             'Protected activity survived 403');
      await page.unroute('**/api/v1/home/overview?*');
      return {listCleared:true, drawerCleared:true, syntheticRevocation:true};
    });
    assert(mutations.length === 0, 'Read/inspect flow emitted a mutation request');
    assert(errors.length === 0, 'Browser page error');
    return {status:'PASS', checks:results, mutationRequests:mutations, pageErrors:errors,
      limitations:['Synthetic fixture, built frontend and actual read APIs; 403 is an explicit routed fixture.',
        'No provider inference, native decisions, real screen-reader speech or true browser 200% zoom measured.',
        'This selected browser subset does not certify all 73 acceptance scenarios.']};
  } catch (error) {
    return {status:'FAIL', checks:results, error:error.message, mutationRequests:mutations, pageErrors:errors};
  } finally {
    page.off('request', onRequest);page.off('pageerror', onError);
  }
}
