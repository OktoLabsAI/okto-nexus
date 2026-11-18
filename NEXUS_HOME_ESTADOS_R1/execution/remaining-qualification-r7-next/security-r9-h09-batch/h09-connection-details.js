async page => {
  const cfg=__CONFIG__,checks=[],requests=[];
  const check=(id,ok)=>{checks.push({id,ok});if(!ok)throw Error(id);};
  page.on('request',r=>requests.push({method:r.method(),path:new URL(r.url()).pathname}));
  try {
    await page.getByTestId('home-board').waitFor({timeout:15000});
    const response=await page.request.get(cfg.url+'/api/v1/home/harness-board?presentation_version=2&workspace_id='+encodeURIComponent(cfg.reference.workspace_id));
    check('actual-board-200',response.status()===200);
    const raw=await response.json(),board=raw.data??raw;
    const matches=Object.values(board.columns).flatMap(c=>c.items).filter(x=>x.kind==='harness'&&x.id===cfg.card_id);
    check('exact-registered-card',matches.length===1&&matches[0].connection.binding_id===cfg.reference.binding_id);
    const dto=matches[0];
    check('individual-capability-unavailable',dto.reconnect_available===false&&dto.reconnect_reason===cfg.expected_reason);
    const card=page.locator('[data-home-harness='+JSON.stringify(cfg.card_id)+']');
    const detail=card.locator('details').filter({has:page.locator('summary').filter({hasText:'Connection details'})});
    const summary=detail.locator('summary');
    await summary.click();
    check('actual-details-open',await detail.evaluate(e=>e.open===true));
    await detail.getByText(cfg.expected_reason,{exact:true}).waitFor({state:'visible',timeout:10000});
    check('limitation-visible',await detail.getByText(cfg.expected_reason,{exact:true}).count()===1);
    const actions=await card.locator('button,a,[role="button"]').evaluateAll(xs=>xs.map(x=>({text:(x.textContent??'').trim(),href:x.getAttribute('href')})));
    check('no-individual-daemon-restart-action',actions.every(x=>!/(reconnect|restart|daemon)/i.test(x.text)&&!(x.href&&/^(?:cmd|powershell|file|connector):/i.test(x.href))));
    check('details-has-no-executable-control',await detail.locator('button,a,[role="button"],form').count()===0);
    await summary.focus();
    await summary.press('Enter');
    check('keyboard-only-closes-disclosure',await detail.evaluate(e=>e.open===false));
    await summary.press('Enter');
    check('keyboard-only-reopens-limitation',await detail.evaluate(e=>e.open===true));
    check('no-state-changing-browser-request',requests.every(x=>['GET','HEAD','OPTIONS'].includes(x.method)));
    return {status:'PASS_SUBSET',checks,requests,actions,limits:['No live Connector daemon is registered in this embedded-executor fixture','Pinned actual Connector CLI source proves reconnect is whole-daemon; no restart command executed']};
  }catch(error){return {status:'FAIL',checks,requests,error:String(error),diagnostics:{dialogs:await page.getByRole('dialog').evaluateAll(xs=>xs.map(x=>x.outerHTML.slice(0,100000))).catch(()=>[])}};}
}
