async page=>{
  const cfg={"url": "http://127.0.0.1:56914", "approval_id": "r4request_e0e60d5d5c85da9883bc53d00d82171fbc32eed30543a2684a3cfa8b544c1c07", "recipient": "operator", "home_off": true},checks=[],requests=[];
  page.setDefaultTimeout(9000);page.on('request',r=>requests.push({method:r.method(),path:new URL(r.url()).pathname}));
  await page.addInitScript(()=>{localStorage.setItem('okto-nexus-workspace','ws');localStorage.setItem('okto.nexus.onboarding.completed.v1','true');localStorage.setItem('okto-nexus:metrics-opt-in-prompt-dismissed:1.0.0','test');});
  if(cfg.home_off)await page.addInitScript(()=>localStorage.setItem('okto-nexus-home-operational','disabled'));
  const read=async path=>{const r=await page.request.get(cfg.url+path);if(r.status()!==200)throw Error('Canonical read failed');const v=await r.json();return v.data??v;};
  await page.goto(cfg.url);
  const auth=await read('/api/v1/operator-auth/status');
  if(!auth.authenticated||!auth.local)throw Error('Require canonical loopback human operator');
  if(cfg.home_off){
    await page.getByTestId('home-overview').waitFor();
    if(await page.evaluate(()=>localStorage.getItem('okto-nexus-home-operational'))!=='disabled'||await page.getByTestId('home-follow-up').count())throw Error('Home OFF given missing');
    checks.push({name:'Existing canonical question remains accessible with new Home OFF',status:'PASS'});
  }
  await page.getByTestId('global-attention-button').click();
  const list=await read('/api/v1/attention?state=active&seen=all&limit=50');
  const item=list.items.find(x=>x.source_id===cfg.approval_id);
  if(!item)throw Error('Exact old question absent from canonical global queue');
  const button=page.getByTestId('attention-open-'+item.attention_id);await button.waitFor();await button.click();
  const dialog=page.getByTestId('attention-inspection');await dialog.waitFor();
  const detail=await read('/api/v1/approvals/'+encodeURIComponent(cfg.approval_id));
  const proposal=detail.request_payload.kwargs;
  if(proposal.approval_key.canonical_request_id!==cfg.approval_id)throw Error('Question changed');
  if(cfg.recipient==='subject'){
    if(item.kind!=='question_waiting_for_agent'||item.allowed_actions.includes('respond_native'))throw Error('Operator acquired agent answer authority');
    if(await dialog.getByRole('button',{name:'Send answer',exact:true}).count())throw Error('Operator sees agent answer control');
    const body={client_intent_id:'own-operator-refusal-proof',decision:'approve',response:{answers:{question:{answers:['Continue']}}}};
    for(const k of ['approval_key','expected_revision','request_hash','cas_token'])body[k]=proposal[k];
    const refusal=await page.request.post(cfg.url+'/api/v1/runtime-management/runtime/approval-decisions',{headers:{'x-nexus-ui':'1'},data:body});
    const raw=await refusal.json();
    if(refusal.status()!==403)throw Error('Wrong recipient not rejected by canonical API');
    checks.push({name:'Operator inspects agent question without personification',status:'PASS',kind:item.kind,allowed_actions:item.allowed_actions});
    checks.push({name:'Canonical API refuses wrong human recipient before effect',status:'PASS',http:refusal.status(),code:raw.error?.code,possible_effect:raw.error?.possible_effect});
  }else{
    const form=dialog.getByTestId('native-approval-input');await form.locator('form').waitFor();
    await form.getByRole('listbox').selectOption('0');
    const accepted=page.waitForResponse(r=>r.request().method()==='POST'&&r.url().endsWith('/approval-decisions'));
    await form.getByRole('button',{name:'Send answer',exact:true}).click();
    const r=await accepted,body=await r.json();
    if(r.status()!==202||body.native_stage!=='DISPATCH_PENDING'||body.possible_effect!==false)throw Error('Old canonical question was not decidable with Home OFF');
    await dialog.getByTestId('canonical-native-status').waitFor();
    checks.push({name:'Old pending human question decided canonically with Home OFF',status:'PASS',http:r.status(),decision_id:body.decision_id,native_stage:body.native_stage,native_application:'NOT_EXECUTED'});
  }
  return {status:'PASS_DECLARED_SCOPE',checks,requests,approval_id:cfg.approval_id,
    advanced_authority_scenario:'NOT_RUN_NO_RESTRICTED_HUMAN_ROLE_GIVEN',
    limits:['Synthetic canonical native peer; no provider application','Home-OFF branch only; interception-OFF generic approval not exercised']};
}
