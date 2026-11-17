async page=>{
 const checks=[],requests=[],errors=[];page.setDefaultTimeout(10000);
 page.on('request',r=>requests.push({method:r.method(),url:r.url()}));
 page.on('pageerror',e=>errors.push(e.message));
 const check=(name,ok,data={})=>{checks.push({name,status:ok?'PASS':'FAIL',...data});if(!ok)throw Error(name);};
 try{
  await page.getByRole('dialog').getByRole('button',{name:'Close modal',exact:true}).click();
  await page.getByRole('dialog').waitFor({state:'detached'});
  const needs=page.getByRole('region',{name:'Needs you',exact:true});
  await needs.getByRole('button',{name:'Review update',exact:true}).first().click();
  await page.getByRole('dialog').waitFor();
  const target=JSON.parse(new URL(page.url()).searchParams.get('home_target'));
  check('Needs-you update retains an explicit canonical target',!!target&&target.workspace_id==='ws'&&target.kind!=='agent',{target});
  await page.screenshot({path:'output/playwright/qc05/needs-update-context.png',fullPage:false});
  await page.getByRole('dialog').getByRole('button',{name:'Close modal',exact:true}).click();
  await page.getByRole('dialog').waitFor({state:'detached'});
  await page.setViewportSize({width:360,height:800});
  const menu=page.getByRole('button',{name:'Open navigation',exact:true});if(await menu.count())await menu.click();
  await page.screenshot({path:'output/playwright/qc05/mobile-navigation.png',fullPage:false});
  const nav=page.getByRole('list',{name:'Main destinations',exact:true});
  check('360 navigation preserves four basic destinations',JSON.stringify(await nav.getByRole('button').allTextContents())===JSON.stringify(['Home','Conversations','Graph','Artifacts']));
  const dismiss=page.getByRole('button',{name:'Close navigation',exact:true});if(await dismiss.count())await dismiss.click();
  await page.screenshot({path:'output/playwright/qc05/home-mobile-360.png',fullPage:false});
  check('360 Home keeps all three column regions and exact IDs',await page.getByRole('region',{name:'Active',exact:true}).count()===1&&await page.getByRole('region',{name:'Needs you',exact:true}).count()===1&&await page.getByRole('region',{name:'Results',exact:true}).count()===1&&await page.getByRole('heading',{name:'Harness ID: builder',exact:true}).count()===1&&await page.getByRole('heading',{name:'Harness ID: reviewer',exact:true}).count()===1);
  const bounds=await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth}));
  check('360 page has no horizontal document overflow',bounds.scroll<=bounds.width,{bounds});
  check('Mobile and Needs viewing performed no mutations and no JS exceptions',requests.every(r=>r.method==='GET')&&errors.length===0,{errors});
  return{status:'PASS',checks,requests,errors};
 }catch(e){await page.screenshot({path:'output/playwright/qc05/mobile-failure.png'});return{status:'FAIL',message:e.message,checks,requests,errors};}
}
