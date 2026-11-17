async page=>{
 const checks=[],requests=[],errors=[];page.on('request',r=>requests.push({method:r.method(),url:r.url()}));page.on('pageerror',e=>errors.push(e.message));
 const check=(name,ok,data={})=>{checks.push({name,status:ok?'PASS':'FAIL',...data});if(!ok)throw Error(name);};
 try{
  const nav=page.getByRole('list',{name:'Main destinations',exact:true});
  const names=await nav.getByRole('button').allTextContents();
  check('Expanded 360 navigation has exactly four basic destinations',JSON.stringify(names)===JSON.stringify(['Home','Conversations','Graph','Artifacts']),{names});
  await page.screenshot({path:'output/playwright/qc05/mobile-navigation-final.png'});
  await page.getByRole('button',{name:'Close navigation',exact:true}).click();
  const bounds=await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth,focusHidden:!!document.activeElement?.closest('[aria-hidden=true]')}));
  check('Mobile navigation closes without focus in hidden content',!bounds.focusHidden,{bounds});
  check('360 Home retains three semantic regions and both exact public IDs',await page.getByRole('region',{name:'Active',exact:true}).count()===1&&await page.getByRole('region',{name:'Needs you',exact:true}).count()===1&&await page.getByRole('region',{name:'Results',exact:true}).count()===1&&await page.getByRole('heading',{name:'Harness ID: builder',exact:true}).count()===1&&await page.getByRole('heading',{name:'Harness ID: reviewer',exact:true}).count()===1);
  check('No horizontal document overflow at width360',bounds.width===360&&bounds.scroll<=360);
  await page.screenshot({path:'output/playwright/qc05/home-mobile-360-final.png',fullPage:false});
  await page.getByRole('region',{name:'Needs you',exact:true}).scrollIntoViewIfNeeded();
  await page.screenshot({path:'output/playwright/qc05/needs-mobile-360-final.png',fullPage:false});
  await page.getByRole('region',{name:'Results',exact:true}).scrollIntoViewIfNeeded();
  await page.screenshot({path:'output/playwright/qc05/results-mobile-360-final.png',fullPage:false});
  check('Final mobile viewing has no mutation or JS exception',requests.every(r=>r.method==='GET')&&errors.length===0,{errors});
  return{status:'PASS',checks,requests,errors};
 }catch(e){return{status:'FAIL',message:e.message,checks,requests,errors};}
}
