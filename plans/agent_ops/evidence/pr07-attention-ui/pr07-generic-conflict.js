async (page) => {
  const id = 'apr_b5b4a70d6f144aaf995eddaa66bd7514';
  const path = `/api/v1/approvals/${id}/decision`;
  const base = 'http://127.0.0.1:49262';
  const headers = {'x-nexus-ui': '1', Origin: 'http://127.0.0.1:49262'};
  const canonical = await (await page.request.get(`${base}/api/v1/approvals/${id}`)).json();
  if (!canonical.ok || canonical.data.status !== 'pending') throw new Error('Expected the reviewed pending approval');
  const revision = canonical.data.decision_revision;
  let concurrentStatus = null;
  await page.route(`**${path}`, async route => {
    const concurrent = await page.request.post(base + path, {headers, data: {
      decision: 'reject', justification: 'Synthetic concurrent operator decision for stale-CAS QA',
      expected_decision_revision: revision,
    }});
    concurrentStatus = concurrent.status();
    await route.continue();
  }, {times: 1});
  const responsePromise = page.waitForResponse(response => response.url().endsWith(path) && response.request().method() === 'POST');
  await page.getByRole('button', {name: 'Confirm', exact: true}).click();
  const response = await responsePromise;
  const submitted = response.request().postDataJSON();
  const result = await response.json();
  await page.getByText('The approval changed. Its current record has been reloaded; review it before deciding again.').waitFor();
  const final = await (await page.request.get(`${base}/api/v1/approvals/${id}`)).json();
  if (concurrentStatus !== 200 || response.status() !== 409 || submitted.expected_decision_revision !== revision || final.data.status !== 'rejected') {
    throw new Error(JSON.stringify({concurrentStatus, stale: response.status(), submitted, final: final.data.status}));
  }
  console.log(JSON.stringify({case: 'generic stale decision', concurrentStatus, staleStatus: response.status(),
    submittedRevision: submitted.expected_decision_revision, code: result.error?.code,
    finalStatus: final.data.status, finalRevision: final.data.decision_revision, conflictVisible: true}));
}
