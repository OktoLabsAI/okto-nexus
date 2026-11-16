async page=>{
  const expected='r4request_dbc5a52f47eb2961cca024d63b9dca276a876eca21a0d614861b62d037097362';
  const before=await page.getByRole('navigation',{name:'Breadcrumb'}).innerText();
  if(before!=='/ Artifacts')throw Error('Must remain in Artifacts after publication ack and before bell');
  const read=await page.request.get('http://127.0.0.1:62396/api/v1/attention?state=active&seen=all&limit=50');
  const raw=await read.json(),d=raw.data??raw,item=d.items.find(x=>x.source_id===expected);
  if(!item)throw Error('New exact question must already exist while in Artifacts');
  const requests=[];page.on('request',r=>requests.push({method:r.method(),url:r.url()}));
  await page.getByTestId('global-attention-button').click();
  await page.locator('[data-attention-id="'+item.attention_id+'"]').waitFor();
  const after=await page.getByRole('navigation',{name:'Breadcrumb'}).innerText();
  await page.screenshot({path:'NEXUS_UI_R1/execution/evidence/pr07-navigation-arrival/artifacts-only/new-question.png',fullPage:true});
  return {status:after==='/ Needs attention'?'PASS':'FAIL',before,after,source_id:item.source_id,kind:item.kind,attention_id:item.attention_id,requests};
}
