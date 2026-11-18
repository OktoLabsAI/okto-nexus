async page => {
  const cfg=__CONFIG__,checks=[],requests=[],responses=[];
  const check=(id,ok,detail)=>{checks.push({id,ok,detail});if(!ok)throw Error(id);};
  page.on('request',r=>requests.push({method:r.method(),path:new URL(r.url()).pathname}));
  page.on('response',r=>responses.push({method:r.request().method(),path:new URL(r.url()).pathname,status:r.status()}));
  try {
    await page.reload({waitUntil:'domcontentloaded'});
    await page.getByTestId('home-board').waitFor({timeout:15000});
    const response=await page.request.get(cfg.url+'/api/v1/home/harness-board?presentation_version=2&workspace_id='+encodeURIComponent(cfg.reference.workspace_id));
    check('board-200',response.status()===200,response.status());
    const raw=await response.json(),board=raw.data??raw;
    const exact=item=>item.source_id===cfg.owner.source_id&&item.observed_instance_id===cfg.owner.observed_instance_id&&item.generation===cfg.owner.generation;
    if(!cfg.completion){
      const entries=board.unlinked.items.filter(entry=>entry.external.some(exact));
      const cardIds=Object.values(board.columns).flatMap(column=>column.items).filter(item=>item.kind==='harness').map(item=>item.id).sort();
      check('exact-unlinked-instance-no-false-harness',entries.length===1&&JSON.stringify(cardIds)===JSON.stringify([...cfg.baseline_card_ids].sort()),{entry_ids:entries.map(e=>e.id),card_ids:cardIds});
      const report=entries[0].external.find(exact);
      check('real-idle-not-canonical-session',report.observational_only===true&&report.canonical_session_ref===null&&report.activity_state==='idle'&&report.last_report.sequence===1,report);
      await page.getByTestId('home-unlinked').getByRole('button',{name:'View other activity',exact:true}).click();
      const dialog=page.getByRole('dialog',{name:'Activity detail'});
      await dialog.locator('[data-home-activity='+JSON.stringify(entries[0].id)+']').getByRole('button',{name:'View external signal',exact:true}).click();
      const inspector=page.getByTestId('external-instance-'+cfg.owner.observed_instance_id);
      await inspector.waitFor({timeout:10000});
      check('idle-reported-visible',await inspector.getByText('Reported evidence',{exact:true}).count()===1&&/idle/i.test(await inspector.innerText()),true);
      check('no-canonical-result-from-idle',!board.columns.results.items.some(item=>item.kind==='delivery'&&item.entry.external.some(exact)),true);
      await dialog.getByRole('button',{name:'Close modal',exact:true}).click();
    }else{
      const deliveries=board.columns.results.items.filter(item=>item.kind==='delivery'&&item.entry.external.some(exact));
      check('one-exact-reported-delivery',deliveries.length===1,deliveries.map(d=>d.id));
      const delivery=deliveries[0],semantics=delivery.delivery_semantics;
      check('reported-not-native-verified',delivery.result===null&&delivery.completion_evidence==='reported'&&semantics.scope==='external_report'&&semantics.evidence==='reported'&&semantics.execution_outcome==='unknown'&&semantics.task_state==='not_applicable'&&semantics.verification==='unknown',semantics);
      const card=page.locator('[data-home-signal='+JSON.stringify(delivery.id)+']');
      await card.getByText('Completion reported',{exact:true}).waitFor();
      check('not-verified-label',await card.getByText('Not verified by Nexus',{exact:true}).count()===1,true);
      check('no-native-success-label',!/(Task completed|Delivery verified|Turn completed)/.test(await card.innerText()),true);
      await card.getByRole('button',{name:'View result',exact:true}).click();
      const dialog=page.getByRole('dialog',{name:'Canonical attention record',exact:true});
      const episode=dialog.getByTestId('external-completion-episode');
      const completionReference=episode.getByText('hst-security-reported-completion',{exact:true});
      await completionReference.waitFor({state:'visible',timeout:10000});
      const inspector=dialog.getByTestId('external-instance-'+cfg.owner.observed_instance_id);
      await inspector.waitFor({state:'visible',timeout:10000});
      const report=delivery.entry.external.find(exact);
      check('exact-observed-completion-open',
        report.workspace_id===cfg.reference.workspace_id&&report.last_report.sequence===2&&
        report.last_report.current_completion_ref==='hst-security-reported-completion'&&
        await completionReference.count()===1&&
        await inspector.getByText(cfg.owner.source_id,{exact:true}).count()===1&&
        await inspector.getByText(cfg.owner.observed_instance_id,{exact:true}).count()===1&&
        await inspector.getByText(cfg.reference.workspace_id,{exact:true}).count()===1&&
        await inspector.getByText('Instance · generation '+cfg.owner.generation,{exact:true}).count()===1&&
        /Sequence: 2(?:\s|$)/.test(await inspector.innerText()),true);
      await dialog.getByRole('button',{name:'Close modal',exact:true}).click();
    }
    check('browser-passive-only',requests.every(x=>['GET','HEAD','OPTIONS'].includes(x.method)),requests);
    return {status:'PASS_SUBSET',checks,requests,limits:['Typed reported evidence only; productive-table snapshot assertions are separate','No native session correlation, capacity release or verification inferred']};
  }catch(error){
    const dialogs=await page.getByRole('dialog').evaluateAll(nodes=>nodes.map(node=>node.outerHTML.slice(0,100000))).catch(()=>[]);
    return {status:'FAIL',error:String(error),checks,requests,errorDiagnostics:{dialogs,responses}};
  }
}
