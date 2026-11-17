async page=>{
 const requests=[],errors=[],checks=[];page.on('request',r=>requests.push({method:r.method(),url:r.url()}));page.on('pageerror',e=>errors.push(e.message));
 const check=(name,ok,data={})=>{checks.push({name,status:ok?'PASS':'FAIL',...data});if(!ok)throw Error(name);};
 await page.addInitScript(()=>{if(location.protocol==='http:'){localStorage.setItem('okto-nexus-home-operational','enabled');localStorage.setItem('okto-nexus-workspace','ws');localStorage.setItem('okto.nexus.onboarding.completed.v1','true');localStorage.setItem('okto-nexus:metrics-opt-in-prompt-dismissed:1.0.0','test');}});
 await page.goto('http://127.0.0.1:50192');await page.getByTestId('home-follow-up').waitFor();
 check('one Home without classic toggle, named Project visible',await page.getByRole('button',{name:'Use classic Home',exact:true}).count()===0&&await page.getByRole('button',{name:'Use operational Home',exact:true}).count()===0&&await page.getByRole('combobox',{name:'Project',exact:true}).isVisible()&&await page.getByText('Project: Sample project',{exact:false}).isVisible());
 const catalog=page.waitForResponse(r=>r.url().includes('/connections/catalog?')&&r.status()===200);await page.getByRole('button',{name:'Connect or resume',exact:true}).click();const body=await(await catalog).json();
 await page.getByRole('region',{name:'Existing project connections',exact:true}).waitFor();
 check('Connect or resume displays same canonical two-connection catalog',body.items.length===2&&await page.getByRole('button',{name:'Open connection',exact:true}).count()===2,{items:body.items.map(i=>({binding_id:i.binding_id,workspace_id:i.workspace_id}))});
 const exact=body.items.findIndex(i=>i.binding_id==='binding');const opened=page.waitForResponse(r=>new URL(r.url()).pathname.endsWith('/connections/bindings/binding')&&r.status()===200);await page.getByRole('button',{name:'Open connection',exact:true}).nth(exact).click();const binding=await(await opened).json();
 check('existing exact binding is opened by canonical GET without creating work',binding.binding_id==='binding'&&requests.every(r=>r.method==='GET')&&errors.length===0,{binding_id:binding.binding_id,errors});
 return{status:'PASS',checks,requests,errors};
}
