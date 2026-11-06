async (page) => {
  const pending = page.waitForResponse(response => response.url().includes('/handoffs/hof_5d777ee0646848d28ecab5084ca2eb67/verify') && response.request().method() === 'POST');
  await page.getByRole('button', {name: 'Confirm', exact: true}).click();
  const response = await pending;
  const body = response.request().postDataJSON();
  if (response.status() !== 200 || !Number.isInteger(body.claim_epoch)) throw new Error(JSON.stringify({status:response.status(),body}));
  return {case:'handoff verification', status: response.status(), submitted:body};
}
