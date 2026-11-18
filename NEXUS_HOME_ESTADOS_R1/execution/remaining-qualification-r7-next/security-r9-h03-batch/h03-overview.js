async page => {
  const cfg=__CONFIG__,checks=[],requests=[],errors=[];
  const check=(id,ok)=>{checks.push({id,ok});if(!ok)throw Error(id);};
  page.on('request',r=>requests.push({method:r.method(),path:new URL(r.url()).pathname}));
  page.on('pageerror',e=>errors.push(String(e)));
  try {
    await page.reload({waitUntil:'domcontentloaded'});
    await page.getByTestId('home-board').waitFor({timeout:15000});
    const response=await page.request.get(cfg.url+'/api/v1/home/harness-board?presentation_version=2&workspace_id='+encodeURIComponent(cfg.reference.workspace_id));
    check('board-200',response.status()===200);
    const text=await response.text(),raw=JSON.parse(text),board=raw.data??raw;
    const cards=Object.values(board.columns).flatMap(c=>c.items).filter(x=>x.kind==='harness'&&x.connection.binding_id===cfg.reference.binding_id);
    check('exact-canonical-card',cards.length===1);
    const label=cards[0].connection.workspace_label;
    check('public-json-label-bounded',typeof label==='string'&&label.length<=160&&label.includes('HST_BROWSER_PUBLIC_EXECUTED'));
    check('private-json-minimized',!text.includes(cfg.private_token)&&!text.includes(cfg.private_prompt));
    check('json-control-escaped',!text.includes('\x1b'));
    const body=await page.locator('body').innerText();
    check('hostile-label-is-visible-text',body.includes('HST_BROWSER_PUBLIC_EXECUTED'));
    check('private-overview-dom-minimized',!body.includes(cfg.private_token)&&!body.includes(cfg.private_prompt));
    check('no-injected-element',await page.locator('img[onerror*="HST_BROWSER_PUBLIC_EXECUTED"]').count()===0);
    check('handler-never-executed',await page.evaluate(()=>globalThis.HST_BROWSER_PUBLIC_EXECUTED===undefined));
    check('no-pageerrors',errors.length===0);
    check('browser-read-only',requests.every(x=>['GET','HEAD','OPTIONS'].includes(x.method)));
    return {status:'PASS_SUBSET',checks,requests,ansi_observations:{serialized_raw_escape:false,parsed_label_contains_escape:label.includes('\x1b'),dom_text_contains_escape:body.includes('\x1b'),interpretation:'ESC may survive as static text; no terminal ANSI interpretation is claimed'},limits:['Overview/cards only; exact authorized transcript not opened','Artifact/filename hostile DOM not covered']};
  }catch(error){return {status:'FAIL',checks,requests,error:String(error),diagnostics:{errors,dialogs:await page.getByRole('dialog').evaluateAll(xs=>xs.map(x=>x.outerHTML.slice(0,100000))).catch(()=>[])}};}
}
