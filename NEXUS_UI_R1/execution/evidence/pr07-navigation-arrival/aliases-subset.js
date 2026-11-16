async page=>{
  const nav=page.getByTestId('navigation-sidebar');
  await nav.getByRole('button',{name:'Conversations',exact:true}).click();
  const conversations=await page.getByRole('navigation',{name:'Breadcrumb'}).innerText();
  await nav.getByRole('button',{name:'Advanced',exact:true}).click();
  await page.getByTestId('advanced-view').getByRole('button',{name:'Policies',exact:true}).click();
  const policies=await page.getByRole('navigation',{name:'Breadcrumb'}).innerText();
  await page.reload();await page.getByRole('navigation',{name:'Breadcrumb'}).waitFor();
  const reloaded=await page.getByRole('navigation',{name:'Breadcrumb'}).innerText();
  return {status:'SUBSET_ONLY',conversations,policies,reloaded,
    missing_given:'No supported view bookmark or saved-view preference entry exists in App; no invented localStorage key was used'};
}
