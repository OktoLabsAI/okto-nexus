async page => {
  const assert=(v,m)=>{if(!v)throw Error(m);};
  const origin=new URL(page.url()).origin;
  const snapshot=await(await page.request.get(origin+'/api/v1/home/overview')).json();
  const work=snapshot.data.work.items.find(i=>i.display_state==='awaiting_agent');
  assert(work,'other-agent question not followable in Home');
  assert(snapshot.data.attention.items.every(i=>i.kind!=='question_waiting_for_agent'),'other-agent question misclassified as needs-you');
  const requests=[];
  const observe=r=>{if(r.method()==='POST')requests.push(new URL(r.url()).pathname);};
  page.on('request',observe);
  try {
    if(!await page.getByTestId('home-detail').count())await page.getByRole('button',{name:'Inspect Work request',exact:true}).click();
    const drawer=page.getByTestId('home-detail');
    await drawer.getByRole('list',{name:'Recorded runtime events',exact:true}).waitFor();
    const text=await drawer.innerText();
    assert(text.includes(work.detail_target.session_id)&&text.includes(work.detail_target.operation_id),'inspector changed selected session/turn');
    assert(text.includes('Input requested')&&text.includes('Choose the next step')&&text.includes('Read only'),'other-agent request cannot be followed read-only');
    assert(await drawer.getByRole('button',{name:'Send answer',exact:true}).count()===0,'operator can answer for another agent');
    assert(await drawer.getByRole('button',{name:'Deny runtime request',exact:true}).count()===0,'operator can deny for another agent');
    assert(requests.length===0,'inspecting the question caused mutation');
    const visible=await(await page.request.get(origin+'/api/v1/runtime-management/runtime/input-requests')).json();
    assert(visible.items.length===0,'other agent question appears in operator response inbox');
    const all=await(await page.request.get(origin+'/api/v1/attention?state=all')).json();
    const watch=all.data.items.find(i=>i.kind==='question_waiting_for_agent');
    assert(watch,'canonical watch occurrence missing');
    const detail=(await(await page.request.get(origin+'/api/v1/approvals/'+watch.source_id)).json()).data;
    const proposal=detail.request_payload.kwargs;
    const body={client_intent_id:'browser-c02-operator-refusal',decision:'approve',
      response:{answers:{question:{answers:['Stop']}}}};
    for(const key of ['approval_key','expected_revision','request_hash','cas_token'])body[key]=proposal[key];
    const refused=await page.request.post(origin+'/api/v1/runtime-management/runtime/approval-decisions',{data:body});
    assert(refused.status()===403,'canonical API allowed operator impersonation');
    const after=(await(await page.request.get(origin+'/api/v1/approvals/'+watch.source_id)).json()).data;
    assert(after.status==='pending'&&!after.executed_result,'refused operator changed the native decision');
    return {id:'HOME-T-C02',status:'PASS',displayState:work.display_state,target:work.detail_target,
      inputRequestedVisible:true,readOnly:true,answerControls:0,inspectionMutations:0,
      operatorInputRequests:visible.items.length,operatorAttemptStatus:403,approvalAfter:after.status};
  } finally {page.off('request',observe);}
}
