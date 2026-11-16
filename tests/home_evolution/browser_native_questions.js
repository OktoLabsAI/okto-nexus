// Real Home browser, actual canonical native ingress and actual CAS POSTs.
// Requires browser_native_questions_fixture.py --case input; ephemeral auth only.
async page => {
  const assert=(v,m)=>{if(!v)throw Error(m);};
  page.setDefaultTimeout(10000);
  const origin=new URL(page.url()).origin, checks=[],posts=[];
  const observe=request=>{if(request.method()==='POST'&&request.url().endsWith('/runtime/approval-decisions')) {
    const body=request.postDataJSON(); posts.push({approval:body.approval_key.canonical_request_id,
      revision:body.expected_revision,decision:body.decision,response:body.response});
  }};
  page.context().on('request',observe);
  const home=await(await page.request.get(origin+'/api/v1/home/overview')).json();
  const occurrence=home.data.attention.items.find(i=>i.kind==='native_question_pending');
  assert(occurrence,'missing current canonical question');
  const frozen=await(await page.request.get(origin+'/__fixture_test_identity')).json();
  const second=await page.context().newPage();
  let release;
  try {
    await page.getByRole('button',{name:'Open question',exact:true}).click();
    const question=page.getByRole('listbox',{name:'Choose the next step',exact:true});
    await question.waitFor();
    const presentation=await question.evaluate(el=>({multiple:el.multiple,options:[...el.options].map(o=>o.textContent)}));
    assert(presentation.multiple,'native multiple selection type lost');
    assert(JSON.stringify(presentation.options)===JSON.stringify(['Continue','Stop','Write another answer']),'native choices changed');
    const drawer=page.getByTestId('home-detail');
    assert((await drawer.innerText()).includes(occurrence.source_id),'wrong canonical request opened');
    assert((await drawer.innerText()).includes('Proceed with the reviewed work'),'description lost');
    checks.push({id:'HOME-T-C01',status:'PASS',request:occurrence.source_id,presentation});
    await second.clock.setFixedTime(new Date(frozen.frozen_time));
    await second.goto(origin);
    await second.getByRole('button',{name:'Open question',exact:true}).click();
    const oldQuestion=second.getByRole('listbox',{name:'Choose the next step',exact:true});
    await oldQuestion.waitFor();
    await oldQuestion.selectOption(['1']);
    await question.selectOption(['0']);
    let entered;
    const ready=new Promise(r=>entered=r), gate=new Promise(r=>release=r);
    await second.route('**/runtime/approval-decisions',async route=>{entered();await gate;await route.continue();});
    const oldResponse=second.waitForResponse(r=>r.url().endsWith('/runtime/approval-decisions')&&r.request().method()==='POST');
    await second.getByRole('button',{name:'Send answer',exact:true}).click();
    await ready;
    const newResponse=page.waitForResponse(r=>r.url().endsWith('/runtime/approval-decisions')&&r.request().method()==='POST');
    await page.getByRole('button',{name:'Send answer',exact:true}).click();
    const accepted=await newResponse;
    assert(accepted.status()===202,'first actual CAS failed');
    release();
    const refused=await oldResponse;
    assert(refused.status()===409,'stale actual CAS did not conflict');
    const canonicalError=await refused.json();
    const alert=second.getByTestId('home-detail').getByRole('alert');
    await alert.waitFor();
    const conflict=await alert.innerText();
    await page.evaluate(value=>localStorage.setItem('home-r1-native-question-evidence',JSON.stringify(value)),
      {status:'PARTIAL',checks,stale:409,accepted:202,conflict,canonicalError,posts});
    const reason=canonicalError.error?.message ?? canonicalError.message;
    assert(typeof reason==='string'&&reason.length>0&&conflict.includes(reason),'old tab conflict does not present canonical reason: '+conflict);
    assert(posts.length===2&&posts.every(p=>p.approval===occurrence.source_id),'CAS targeted a different request or replayed');
    checks.push({id:'HOME-T-E08',status:'PASS',accepted:202,stale:409,conflict,posts});
    const result={status:'PASS',checks,scope:'Real built Home, actual HTTP/CAS and synthetic canonical ingress; no provider application claim'};
    await page.evaluate(value=>localStorage.setItem('home-r1-native-question-evidence',JSON.stringify(value)),result);
    return result;
  } finally {
    release?.();
    await second.unrouteAll({behavior:'wait'});
    page.context().off('request',observe);
    await second.close({runBeforeUnload:false});
  }
}
