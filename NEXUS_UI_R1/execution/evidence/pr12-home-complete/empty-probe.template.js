async page=>{
 const cfg=__CFG__,checks=[],requests=[],errors=[],consoleErrors=[];page.setDefaultTimeout(15000);
 page.on('request',r=>requests.push({method:r.method(),url:r.url()}));page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error')consoleErrors.push(m.text());});
 const check=(name,ok,data={})=>{checks.push({name,status:ok?'PASS':'FAIL',...data});if(!ok)throw Error(name);};
 try{
  const response=page.waitForResponse(r=>r.url().includes('/api/v1/home/entries?')&&r.status()===200);await page.goto(cfg.url);await page.getByTestId('home-follow-up').waitFor();const home=(await(await response).json()).data;
  const canonical=await page.evaluate(async url=>{const result={};for(const [name,path] of [['global','/api/v1/attention/summary?state=active&seen=all'],['project','/api/v1/attention/summary?workspace_id=ws&state=active&seen=all']]){const r=await fetch(url+path);result[name]={status:r.status,body:await r.json()};}return result;},cfg.url);
  await page.getByTestId('attention-badge').getByText('0',{exact:true}).waitFor();
  check('T-HOME-10 canonical all-project and project Attention are both exact zero',canonical.global.status===200&&canonical.project.status===200&&canonical.global.body.data.total===0&&canonical.project.body.data.total===0&&home.server_attention.total===0&&home.summary.occurrences.value===0,{canonical,server_attention:home.server_attention,summary:home.summary});
  const absent=async()=>await page.getByRole('button',{name:/Server attention/}).count()===0&&await page.getByRole('heading',{name:'Needs you',exact:true}).count()===0;
  check('zero Attention creates no empty Server or Needs you panel',await absent()&&await page.getByTestId('global-attention-button').isVisible()&&await page.getByTestId('global-attention-button').isEnabled());
  await page.screenshot({path:cfg.out+'/global-project-zero-no-panels.png',fullPage:true});
  const filtered=page.waitForResponse(r=>r.url().includes('/api/v1/home/entries?')&&r.url().includes('quick=needs_you')&&r.status()===200);await page.getByRole('group',{name:'Follow-up filter',exact:true}).getByRole('button',{name:'Needs you',exact:true}).click();const needs=(await(await filtered).json()).data;
  check('Needs you filter remains accessible at zero',needs.total===0&&needs.total_is_exact&&await absent(),{needs});
  await page.getByTestId('global-attention-button').click();await page.getByRole('heading',{name:'Needs attention',exact:true}).waitFor();
  check('global bell still opens the canonical queue at zero',await page.getByRole('heading',{name:'Needs attention',exact:true}).isVisible());
  await page.screenshot({path:cfg.out+'/global-zero-queue-accessible.png',fullPage:true});
  check('empty test uses frozen asset and only GET with zero frontend errors',(await page.locator('script[src]').evaluateAll(ns=>ns.map(n=>n.getAttribute('src')))).some(x=>x.includes('index-BGONNtiX.js'))&&requests.every(r=>r.method==='GET')&&errors.length===0&&consoleErrors.length===0,{errors,consoleErrors});
  return{status:'PASS',checks,requests,errors,consoleErrors,home};
 }catch(e){await page.screenshot({path:cfg.out+'/empty-failure.png',fullPage:true});return{status:'FAIL',message:e.message,checks,requests,errors,consoleErrors};}
}
