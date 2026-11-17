async page=>{
  const posts=[];page.on('request',r=>{if(r.method()==='POST')posts.push(new URL(r.url()).pathname);});
  const row=page.locator('[data-home-item="result_939b4021ada87da03ffa02f62ca667829bafed79759b31ad19f6e8ec166a8fd0"]');
  const response=page.waitForResponse(r=>r.request().method()==='POST'&&r.url().endsWith('/seen'));
  await row.getByRole('button',{name:'Mark seen',exact:true}).click();
  const r=await response;if(r.status()!==200)throw Error('Preference not accepted');
  const after=await page.request.get('http://127.0.0.1:51034/api/v1/home/results?workspace_id=ws&limit=100');
  const raw=await after.json(),result=(raw.data??raw).items.find(x=>x.source_ref.id==='ui-old-unseen');
  return {status:result.view_state==='seen'&&posts.length===1?'PASS':'FAIL',posts,
    result_id:result.id,view_state:result.view_state,source_revision:result.attention.source_revision,
    preference_revision:result.attention.seen_state.revision,
    scope:'Mark-seen CAS only; new result revision publication not executed'};
}
