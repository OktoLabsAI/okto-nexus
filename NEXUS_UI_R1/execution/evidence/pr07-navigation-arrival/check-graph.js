async page=>{
  const before=await page.getByRole('navigation',{name:'Breadcrumb'}).innerText();
  const requests=[];page.on('request',r=>requests.push({method:r.method(),url:r.url()}));
  await page.getByTestId('global-attention-button').click();
  await page.getByTestId('attention-view').waitFor();
  const text=await page.getByTestId('attention-view').innerText();
  return {before,after:await page.getByRole('navigation',{name:'Breadcrumb'}).innerText(),text,requests};
}
