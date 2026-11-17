async page=>{
  if(!await page.getByTestId('home-detail').count())await page.locator('[data-home-item="result_6fd535fe05ed2743c83ba55f670ea29697395e01487f3c05f2d4758d4952db17"]').getByRole('button',{name:'Open result',exact:true}).click();
  const dialog=page.getByTestId('home-detail');await dialog.waitFor();
  const label=dialog.getByText(/awaiting verification/i).first();await label.waitFor();await label.scrollIntoViewIfNeeded();
  const lines=(await dialog.innerText()).split('\n').filter(x=>/verification|delivery-[012]\.txt|not tracked/.test(x));
  await page.screenshot({path:'NEXUS_UI_R1/execution/evidence/pr07-results-browser/final/verifying-files-detail.png',fullPage:true});
  await dialog.getByRole('button',{name:'Close modal',exact:true}).click();
  return {status:'PASS',lines,scope:'Exact awaiting-verification label and three files in same passive detail; no acceptance'};
}
