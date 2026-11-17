async page=>{
  const origin='http://127.0.0.1:51034',checks=[],requests=[];
  page.setDefaultTimeout(10000);page.on('request',r=>requests.push({method:r.method(),path:new URL(r.url()).pathname}));
  await page.addInitScript(()=>{localStorage.setItem('okto-nexus-home-operational','enabled');localStorage.setItem('okto-nexus-workspace','ws');localStorage.setItem('okto.nexus.onboarding.completed.v1','true');localStorage.setItem('okto-nexus:metrics-opt-in-prompt-dismissed:1.0.0','test');});
  const get=async path=>{const r=await page.request.get(origin+path);if(r.status()!==200)throw Error('Read failed '+path);const raw=await r.json();return raw.data??raw;};
  const data=await get('/api/v1/home/results?workspace_id=ws&limit=100');
  const main=data.items.find(x=>x.source_ref.id==='ui-handoff-0'),old=data.items.find(x=>x.source_ref.id==='ui-old-unseen'),untracked=data.items.find(x=>x.source_ref.id==='ui-untracked');
  if(main.artifacts.length!==3||main.verification_state!=='VERIFYING')throw Error('Expected one correlated VERIFYING result with3files');
  checks.push({name:'One correlated result carries three authorized files',status:'PASS',id:main.id,artifacts:main.artifacts,verification:main.verification_state});
  const outside=await get('/api/v1/home/results?workspace_id=ui-outside-workspace&limit=100');
  if(!outside.items.some(x=>x.source_ref.id==='ui-outside-result'))throw Error('Offscope result given missing');
  // Prove a small first page omits some actual result, rather than describing
  // an imaginary outside-page row. No reads mark these records viewed.
  const first=await get('/api/v1/home/results?workspace_id=ws&limit=1');
  if(!first.has_more||first.total<2)throw Error('Off-page result given missing');
  await page.goto(origin);await page.getByTestId('home-follow-up').waitFor();
  const reveal=async()=>{
    const expands=page.getByTestId('home-follow-up').getByRole('button',{name:'Expand',exact:true});
    while(await expands.count())await expands.first().click();
    for(let i=0;i<12;i++){
      const more=page.getByRole('button',{name:'Load more items',exact:true});
      if(!await more.count())break;await more.first().click();
      await page.waitForTimeout(150);
    }
  };
  await reveal();
  const oldRow=page.locator('[data-home-item="'+old.id+'"]');
  await oldRow.waitFor();
  checks.push({name:'Old retained unseen reachable in default recent window',status:'PASS',id:old.id,created_at:old.created_at,view_state:old.view_state});
  const filtered=page.waitForResponse(r=>r.url().includes('/home/entries?')&&r.url().includes('quick=results')&&r.status()===200);
  await page.getByRole('group',{name:'Follow-up filter',exact:true}).getByRole('button',{name:'Results',exact:true}).click();
  await filtered;await page.getByTestId('home-follow-up').getByRole('button',{name:'Expand',exact:true}).first().waitFor();
  await reveal();await oldRow.waitFor();
  checks.push({name:'Old unseen still reachable through Results filter',status:'PASS',id:old.id});
  const row=page.locator('[data-home-item="'+main.id+'"]');await row.waitFor();
  const files=await row.locator('[aria-label="Authorized artifact references"]').innerText();
  if(!['delivery-0.txt','delivery-1.txt','delivery-2.txt'].every(x=>files.includes(x)))throw Error('Files not reunited in actual DOM');
  const unknown=page.locator('[data-home-item="'+untracked.id+'"]');await unknown.waitFor();
  const unknownText=await unknown.innerText();
  if(!unknownText.includes('Recent · seen state not tracked'))throw Error('Untracked source mislabeled');
  checks.push({name:'Untracked result uses Recent label',status:'PASS',id:untracked.id});
  await row.getByRole('button',{name:'Open result',exact:true}).click();
  const dialog=page.getByTestId('home-detail');await dialog.waitFor();
  const text=await dialog.innerText();
  checks.push({name:'Open correlated VERIFYING result',status:/verif/i.test(text)?'PASS':'FAIL',verification_label:/verif/i.test(text),dialogs:await page.getByRole('dialog').count()});
  await page.screenshot({path:'NEXUS_UI_R1/execution/evidence/pr07-results-browser/final/verifying-result.png',fullPage:true});
  await dialog.getByRole('button',{name:'Close modal',exact:true}).click();
  if(requests.some(r=>!['GET','HEAD','OPTIONS'].includes(r.method)))throw Error('Unexpected mutation during viewing');
  return {status:checks.every(c=>c.status==='PASS')?'PASS':'FAIL',checks,requests,
    outside_result_ids:outside.items.map(x=>x.id),first_page:{total:first.total,has_more:first.has_more},
    limits:['Historical synthetic receipt facts, not complete native operation histories','Read/view stage only; revision publication not exercised']};
}
