async page=>{
  const cfg=__FIXTURE_CONFIG__,checks=[],requests=[],responses=[],errors=[];
  page.setDefaultTimeout(8000);
  const capture=p=>{p.on('request',r=>requests.push({method:r.method(),url:r.url()}));p.on('response',async r=>{
    const record={url:r.url(),status:r.status()};if(r.request().method()==='POST'&&r.url().endsWith('/approval-decisions')){try{record.body=await r.json();}catch{}}responses.push(record);
  });p.on('pageerror',e=>errors.push(e.message));p.on('dialog',d=>{if(d.type()==='beforeunload')void d.accept();});};
  const check=(name,ok,data={})=>{checks.push({name,status:ok?'PASS':'FAIL',...data});if(!ok)throw Error(name);};
  const init=()=>{localStorage.setItem('okto-nexus-home-operational','enabled');localStorage.setItem('okto-nexus-workspace','ws');localStorage.setItem('okto.nexus.onboarding.completed.v1','true');localStorage.setItem('okto-nexus:metrics-opt-in-prompt-dismissed:1.0.0','test');};
  const open=async p=>{await p.goto(cfg.url);await p.getByTestId('home-follow-up').waitFor();
    const expands=p.getByTestId('home-follow-up').getByRole('button',{name:'Expand',exact:true});
    while(await expands.count())await expands.first().click();
    await p.getByRole('button',{name:/^Open (question|approval)$/}).first().click();await p.getByTestId('native-approval-input').locator('form').waitFor();};
  capture(page);await page.addInitScript(init);await page.setViewportSize({width:1440,height:1100});
  let second;
  try{
    await open(page);
    const dialog=page.getByTestId('home-detail'),form=page.getByTestId('native-approval-input');
    await form.getByRole('listbox').selectOption('custom');
    await form.getByRole('textbox').fill('own unsent human question draft');
    await dialog.getByRole('button',{name:'Show work details',exact:true}).click();
    await dialog.getByText('Discard unsaved changes?',{exact:true}).waitFor();
    await dialog.getByRole('button',{name:'Keep editing',exact:true}).click();
    check('human question context switch guard preserves exact draft',(await form.getByRole('textbox').inputValue())==='own unsent human question draft'&&await page.getByRole('dialog').count()===1);
    await page.keyboard.press('Escape');await dialog.getByText('Discard unsaved changes?',{exact:true}).waitFor();
    await dialog.getByRole('button',{name:'Keep editing',exact:true}).click();
    check('human question Escape guard keeps draft',(await form.getByRole('textbox').inputValue())==='own unsent human question draft');
    await dialog.getByRole('button',{name:'Show work details',exact:true}).click();
    await dialog.getByRole('button',{name:'Discard changes',exact:true}).click();
    await form.waitFor({state:'detached'});
    check('explicit discard changes only inner context, one root dialog',await page.getByRole('dialog').count()===1);
    await dialog.getByRole('button',{name:/^Open (question|approval)$/}).click();
    await form.locator('form').waitFor();await form.getByRole('listbox').selectOption('0');
    second=await page.context().newPage();capture(second);await second.addInitScript(init);await open(second);
    await second.getByTestId('native-approval-input').getByRole('listbox').selectOption('0');
    await page.screenshot({path:`${cfg.outputDirectory}/human-reviewed-before-submit.png`,fullPage:true});
    const predicate=r=>r.request().method()==='POST'&&r.url().endsWith('/approval-decisions');
    const one=page.waitForResponse(predicate),two=second.waitForResponse(predicate);
    await Promise.all([page.getByRole('button',{name:'Send answer',exact:true}).click(),second.getByRole('button',{name:'Send answer',exact:true}).click()]);
    const result=await Promise.all([one,two]);
    const actual=await Promise.all(result.map(async r=>({status:r.status(),body:await r.json()})));
    check('two actual browser tabs canonical CAS returns202 and409',JSON.stringify(actual.map(x=>x.status).sort())===JSON.stringify([202,409]),{actual});
    const accepted=actual.find(x=>x.status===202).body;
    check('accepted human decision is dispatch pending, not applied',accepted.native_stage==='DISPATCH_PENDING'&&accepted.possible_effect===false,{canonical_state:accepted.canonical_state,native_stage:accepted.native_stage,possible_effect:accepted.possible_effect});
    const winner=result[0].status()===202?page:second;
    await winner.getByTestId('canonical-native-status').waitFor();
    const visible=await winner.getByTestId('canonical-native-status').innerText();
    check('UI distinguishes recorded decision from provider application',visible.includes('DISPATCH_PENDING')&&visible.includes('does not prove application by the provider'),{visible});
    await winner.screenshot({path:`${cfg.outputDirectory}/human-canonical-dispatch-pending.png`,fullPage:true});
    check('only allowlisted native decision POSTs occurred',requests.filter(r=>r.method==='POST').length===2&&requests.filter(r=>r.method==='POST').every(r=>r.url.endsWith('/approval-decisions')),{posts:requests.filter(r=>r.method==='POST')});
    check('human focal has no page exceptions',errors.length===0,{errors});
    return{status:'PASS',checks,requests,responses,errors,scope:'human origin intact; synthetic admitted WSS, canonical decision persistence only; no dispatch/native provider application',session:cfg.original_session};
  }catch(e){await page.screenshot({path:`${cfg.outputDirectory}/human-failure.png`,fullPage:true});return{status:'FAIL',message:e.message,checks,requests,responses,errors};}
  finally{if(second)await second.close();}
}
