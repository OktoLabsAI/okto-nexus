async page => {
  const requests=[];page.on('request',r=>requests.push({method:r.method(),url:r.url()}));
  page.setDefaultTimeout(10000);
  await page.setViewportSize({width:1440,height:1100});
  await page.getByTestId('navigation-sidebar').getByRole('button',{name:'Home',exact:true}).click();
  await page.getByTestId('home-follow-up').waitFor();
  await page.getByRole('group',{name:'Follow-up filter',exact:true}).getByRole('button',{name:'All',exact:true}).click();
  // The All filter may already be selected after an earlier read-only probe.
  // Read the real scoped page; never require a duplicate UI fetch or mock it.
  const response=await page.request.get(new URL(page.url()).origin+'/api/v1/home/entries?workspace_id=ws&quick=all');
  if(response.status()!==200)throw Error('Canonical scoped entries unavailable');
  const body=await response.json(),groups=(body.data??body).items;
  const pair=groups.flatMap(g=>g.children.map(e=>({g,e}))).find(({e})=>e.kind==='session'&&e.target?.session_id==='ui04-no-turn-session');
  if(!pair)throw Error('Exact canonical no-turn session absent from actual API page');
  const group=page.locator(`[data-home-group="${pair.g.id}"]`);
  const expand=group.getByRole('button',{name:'Expand',exact:true});if(await expand.count())await expand.click();
  await group.locator(`[data-home-entry="${pair.e.id}"] [data-home-entry-open]`).click();
  const dialog=page.getByTestId('home-detail');
  const output=dialog.getByRole('region',{name:'Session execution output',exact:true});
  await output.getByText('ui04-no-turn-session',{exact:true}).waitFor();
  // Session-ID rendering precedes the real events response. Snapshot only the
  // completed empty-stream fixture, rather than comparing loading to ready.
  await output.getByText('Following live events',{exact:true}).waitFor();
  await output.getByText('No activity to display yet.',{exact:true}).waitFor();
  const snapshot=async()=>({dialogs:await page.getByRole('dialog').count(),outputs:await output.count(),
    viewer:await output.innerText(),width:(await dialog.boundingBox()).width,className:await dialog.getAttribute('class')});
  const normal=await snapshot();
  await dialog.getByRole('button',{name:'Expand modal',exact:true}).click();
  await dialog.getByRole('button',{name:'Restore modal',exact:true}).waitFor();
  const expanded=await snapshot();
  await page.screenshot({path:'NEXUS_UI_R1/execution/evidence/pr07-navigation/panel-expanded.png',fullPage:true});
  await dialog.getByRole('button',{name:'Restore modal',exact:true}).click();
  await dialog.getByRole('button',{name:'Expand modal',exact:true}).waitFor();
  const restored=await snapshot();
  await page.screenshot({path:'NEXUS_UI_R1/execution/evidence/pr07-navigation/panel-restored.png',fullPage:true});
  const pass=[normal,expanded,restored].every(x=>x.dialogs===1&&x.outputs===1)&&
    normal.viewer===expanded.viewer&&normal.viewer===restored.viewer&&
    expanded.width>normal.width&&restored.width===normal.width&&normal.className===restored.className&&expanded.className!==normal.className&&
    requests.every(x=>['GET','HEAD','OPTIONS'].includes(x.method));
  await dialog.getByRole('button',{name:'Close modal',exact:true}).click();
  return {status:pass?'PASS':'FAIL',normal,expanded,restored,target:pair.e.target,requests,
    scope:'Parent drawer expand/restore, exact retained session, one passive output; no native zoom, output-growth, provider or assistive-technology speech claim.'};
}
