async page=>{
 const checks=[];
 const bounds=await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth,focusHidden:!!document.activeElement?.closest('[aria-hidden=true]'),focusId:document.activeElement?.getAttribute('data-testid')}));
 checks.push({name:'Escape closes mobile navigation and returns focus to visible toggle',status:!bounds.focusHidden&&bounds.focusId==='sidebar-toggle'?'PASS':'FAIL',bounds});
 checks.push({name:'No horizontal document overflow at360',status:bounds.width===360&&bounds.scroll<=360?'PASS':'FAIL'});
 checks.push({name:'Three regions and both public IDs remain at360',status:await page.getByRole('region',{name:'Active',exact:true}).count()===1&&await page.getByRole('region',{name:'Needs you',exact:true}).count()===1&&await page.getByRole('region',{name:'Results',exact:true}).count()===1&&await page.getByRole('heading',{name:'Harness ID: builder',exact:true}).count()===1&&await page.getByRole('heading',{name:'Harness ID: reviewer',exact:true}).count()===1?'PASS':'FAIL'});
 await page.screenshot({path:'output/playwright/qc05/home-mobile-360-final.png'});
 await page.getByRole('heading',{name:'Harness ID: reviewer',exact:true}).scrollIntoViewIfNeeded();
 await page.screenshot({path:'output/playwright/qc05/needs-mobile-360-final.png'});
 await page.getByRole('region',{name:'Results',exact:true}).scrollIntoViewIfNeeded();
 await page.screenshot({path:'output/playwright/qc05/results-mobile-360-final.png'});
 return{status:checks.every(c=>c.status==='PASS')?'PASS':'FAIL',checks};
}
