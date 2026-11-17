async page=>{
 const out='D:/Projetos/Techridy/okto_labs_okto_nexus/output/playwright/ui-board-final',requests=[];
 page.on('request',r=>requests.push({method:r.method(),url:r.url()}));
 const flow=page.getByTestId('project-connect-detail');
 if(await flow.count())await flow.getByRole('button',{name:'Close and keep attempt',exact:true}).click();
 await page.setViewportSize({width:1440,height:1100});await page.waitForTimeout(300);
 await page.getByRole('heading',{name:'Follow-up',exact:true}).evaluate(el=>el.scrollIntoView({block:'start'}));
 await page.screenshot({path:out+'/desktop-board-clear.png',fullPage:false});
 const desktop=await page.locator('[data-home-column] > div > h3').evaluateAll(ns=>ns.map(n=>({text:n.textContent,rect:n.getBoundingClientRect().toJSON()})));
 await page.setViewportSize({width:360,height:1000});await page.waitForTimeout(300);
 const mobile=[];
 for(const name of ['active','needs_you','results']){
  const heading=page.locator('[data-home-column="'+name+'"]').getByRole('heading',{level:3});
  await heading.evaluate(el=>el.scrollIntoView({block:'start'}));
  mobile.push({name,rect:await heading.boundingBox()});
  await page.screenshot({path:out+'/mobile-'+name+'-clear.png',fullPage:false});
 }
 const result={status:requests.every(r=>r.method==='GET')?'PASS':'FAIL',scope:'Supplementary read-only captures; no new Test/Finish or human interaction.',desktop,mobile,requests};
 return result;
}
