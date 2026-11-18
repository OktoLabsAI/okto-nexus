// PREPARED ONLY. Root-gated executor supplies public IDs and PRIVATE own cookie.
// Oracle counterpart of browser-s3.js; original and its manifest stay unchanged.
async page=>{
  const cfg=__CONFIG__;
  const origin=new URL(cfg.origin);
  if(origin.protocol!=='http:'||!['127.0.0.1','localhost'].includes(origin.hostname))throw Error('Own loopback fixture required');
  if(![cfg.workspace_id,cfg.binding_id,cfg.attention_id].every(id=>typeof id==='string'&&id.length>0))throw Error('Canonical public readiness IDs required');
  const checks=[],writes=[];
  const check=(id,pass,actual)=>{checks.push({id,pass:!!pass,actual});if(!pass)throw Error(id);};
  page.on('request',request=>{if(!['GET','HEAD','OPTIONS'].includes(request.method()))writes.push({method:request.method(),path:new URL(request.url()).pathname});});
  await page.context().setExtraHTTPHeaders({'X-Nexus-UI':'1','X-Nexus-Operator-Session-Required':'1'});
  await page.setViewportSize({width:1440,height:1000});
  const nav=page.getByTestId('navigation-sidebar');
  const home=async()=>{await nav.getByRole('button',{name:'Home',exact:true}).click();};
  const project=()=>page.getByRole('combobox',{name:'Project',exact:true});
  const classic=async()=>{await page.getByRole('heading',{name:'Harness sessions',exact:true}).waitFor();};
  const settings=async()=>{
    await nav.getByRole('button',{name:'Advanced',exact:true}).click();
    const index=page.getByTestId('advanced-view');await index.waitFor();
    // The canonical ID remains Settings; its public registry label is System settings.
    await index.getByRole('button',{name:/^System settings\b/}).click();
    const preference=page.getByTestId('home-display-preference');await preference.waitFor();return preference;
  };
  const preferenceValue=()=>page.evaluate(()=>localStorage.getItem('okto-nexus-home-operational'));
  try{
    await page.goto(cfg.origin);await nav.waitFor();await home();await classic();
    check('shipped-classic-default',await preferenceValue()!=='enabled',await preferenceValue());
    await project().selectOption(cfg.workspace_id);
    check('initial-project-exact',await project().inputValue()===cfg.workspace_id,await project().inputValue());

    const enable=await settings();await enable.getByRole('button',{name:'Use operational Home',exact:true}).click();
    await enable.getByRole('button',{name:'Use classic Home',exact:true}).waitFor();
    check('Settings-enables-presentation',await preferenceValue()==='enabled',await preferenceValue());
    await home();await page.getByTestId('home-board').waitFor();
    check('three-board-column-elements',await page.locator('[data-home-column]').count()===3,await page.locator('[data-home-column]').count());
    for(const column of ['active','needs_you','results'])await page.locator('[data-home-column='+column+']').waitFor({state:'visible'});
    check('operational-project-exact',await project().inputValue()===cfg.workspace_id,await project().inputValue());
    const response=await page.request.get(cfg.origin+'/api/v1/home/harness-board?presentation_version=2&workspace_id='+encodeURIComponent(cfg.workspace_id));
    check('canonical-Home-projection-200',response.status()===200,response.status());
    const raw=await response.json(),board=raw.data??raw;
    const cards=Object.values(board.columns).flatMap(column=>column.items).filter(item=>item.kind==='harness');
    const matches=cards.filter(item=>item.connection.binding_id===cfg.binding_id&&item.connection.workspace_id===cfg.workspace_id);
    check('exact-CLI-binding-in-canonical-projection',matches.length===1,{bindings:matches.map(item=>({id:item.id,binding_id:item.connection.binding_id,workspace_id:item.connection.workspace_id}))});
    await page.locator('[data-home-harness='+JSON.stringify(matches[0].id)+']').waitFor({state:'visible'});
    check('canonical-CLI-card-visible-in-Home',true,{card_id:matches[0].id});

    const disable=await settings();await disable.getByRole('button',{name:'Use classic Home',exact:true}).click();
    await disable.getByRole('button',{name:'Use operational Home',exact:true}).waitFor();
    check('Settings-rolls-back-presentation',await preferenceValue()==='disabled',await preferenceValue());
    await home();await classic();
    check('operational-board-unmounted',await page.getByTestId('home-board').count()===0,true);
    check('rollback-project-preserved',await project().inputValue()===cfg.workspace_id,await project().inputValue());
    await page.getByTestId('global-attention-button').click();await page.getByTestId('attention-heading').waitFor();
    await page.getByTestId('attention-open-'+cfg.attention_id).waitFor();
    check('known-global-question-exposed',true,{attention_id:cfg.attention_id});
    check('zero-non-read-browser-requests',writes.length===0,writes);
    return {status:'PASS_BROWSER_S3_SUBSET',checks,writes,classic_default:true,settings_enable:true,operational_exact_binding:true,settings_rollback:true,classic_sessions_summary:true,exact_global_question:true,selected_project_preserved:true,productive_posts:0,limits:['UI presentation toggle and exact queue item only','Classic Conversations navigation itself was not exercised','PID/birth/generation/roots/profile/checkpoint/grant invariants require paired external snapshots','No direct operational-Home localStorage writes; only the actual Settings callback changes preference']};
  }catch(error){
    return {status:'INCOMPLETE_BROWSER_S3',checks,writes,error:String(error),url:page.url(),limits:['No interpretation as a product defect without DOM/HTTP diagnosis','No paired CLI activity/invariant claim from this JS alone']};
  }
}
