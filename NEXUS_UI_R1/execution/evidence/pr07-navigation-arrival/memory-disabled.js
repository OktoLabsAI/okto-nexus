async page=>{
  await page.getByTestId('navigation-sidebar').getByRole('button',{name:'Advanced',exact:true}).click();
  await page.getByTestId('advanced-view').waitFor();
  const info=await page.request.get('http://127.0.0.1:51859/api/v1/info');const raw=await info.json(),d=raw.data??raw;
  const hidden=await page.getByTestId('advanced-view').getByRole('button',{name:'Shared memory',exact:true}).count()===0;
  // No product view-URL contract exists. This is explicitly an unknown query,
  // not an invented supported Memory link or proof of backend ACL refusal.
  await page.goto('http://127.0.0.1:51859/?view=Memory');
  await page.getByRole('navigation',{name:'Breadcrumb'}).waitFor();
  const destination=await page.getByRole('navigation',{name:'Breadcrumb'}).innerText();
  const memory=await page.request.get('http://127.0.0.1:51859/api/v1/memory?workspace=ws');
  return {memory_enabled:d.features.feature_memory,hidden,unknown_query_destination:destination,memory_http_status:memory.status(),
    status:'PASS_VISIBILITY_ONLY',direct_view_url:'NOT_RUN_NO_PRODUCT_CONTRACT'};
}
