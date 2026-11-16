async page=>{
  const r=await page.request.get('http://127.0.0.1:51859/api/v1/attention?state=active&seen=all&limit=50');const raw=await r.json(),d=raw.data??raw;
  const wanted='r4request_5e373ef44a684313ac3c64f83bcddf153d231a076064815e2b01d278697a1fb8';
  const item=d.items.find(x=>x.source_id===wanted);
  if(!item) return {status:'FAIL',reason:'new canonical question missing from global attention',statusCode:r.status(),items:d.items.map(x=>({kind:x.kind,source_id:x.source_id}))};
  await page.locator('[data-attention-id="'+item.attention_id+'"]').waitFor();
  await page.screenshot({path:'NEXUS_UI_R1/execution/evidence/pr07-navigation-arrival/graph-new-question.png',fullPage:true});
  await page.getByTestId('navigation-sidebar').getByRole('button',{name:'Artifacts',exact:true}).click();
  return {status:'PASS',source_id:item.source_id,attention_id:item.attention_id,kind:item.kind,after:await page.getByRole('navigation',{name:'Breadcrumb'}).innerText()};
}
