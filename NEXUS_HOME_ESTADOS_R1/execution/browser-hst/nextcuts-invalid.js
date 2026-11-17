async page=>{
 const cfg=__CONFIG__,checks=[],requests=[];let bad=null;const check=(id,ok,detail)=>{checks.push({id,ok,detail});if(!ok)throw Error(id);};
 try{
  const [server_id,executor_id,workspace_id]=JSON.parse(cfg.selected),target={kind:'session',server_id,executor_id,workspace_id,session_id:'hst-not-a-canonical-session'};
  const url=new URL(cfg.url);url.searchParams.set('home_target',JSON.stringify(target));bad=await page.context().newPage();bad.on('request',r=>requests.push({method:r.method(),path:new URL(r.url()).pathname}));
  const denied=bad.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/home/target'&&[403,404].includes(r.status()),{timeout:10000});
  await bad.goto(url.toString(),{waitUntil:'domcontentloaded'});const response=await denied;await bad.waitForTimeout(500);
  check('invalid-reference-denied',response.status()===403||response.status()===404,response.status());
  check('invalid-reference-never-reads-latest-session',requests.filter(x=>x.path.includes('/runtime/sessions/')).every(x=>x.path.includes(target.session_id)),requests.filter(x=>x.path.includes('/runtime/sessions/')));
  check('invalid-reference-zero-write',requests.every(x=>x.method==='GET'),true);
  return {status:'PASS_BROWSER_SUBSET',checks,requests,limits:['Missing exact reference, not foreign-principal preview/counter audit']};
 }catch(error){return {status:'FAIL_OR_INCOMPLETE',error:String(error),checks,requests};}
 finally{if(bad)await bad.close();}
}
