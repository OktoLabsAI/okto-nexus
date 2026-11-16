// Start the own contract fixture, open its URL in an isolated browser, then run-code this file.
async (page) => {
  page.setDefaultTimeout(8000);
  const origin=new URL(page.url()).origin;
  if(!origin.startsWith('http://127.0.0.1:'))throw Error('Own loopback fixture URL required');
  await page.addInitScript(()=>{
    if(!['http:','https:'].includes(location.protocol))return;
    localStorage.setItem('okto-nexus-home-operational','enabled');
    localStorage.setItem('okto.nexus.onboarding.completed.v1','true');
    localStorage.setItem('okto-nexus:metrics-opt-in-prompt-dismissed:1.0.0','test');
  });
  const checks=[],mutations=[],errors=[],directHttpProbes=[];
  const request=r=>{if(new URL(r.url()).origin===origin&&!['GET','HEAD','OPTIONS'].includes(r.method()))mutations.push({method:r.method(),path:new URL(r.url()).pathname,body:r.postDataJSON()});};
  const pageError=e=>errors.push(e.message);
  page.on('request',request);page.on('pageerror',pageError);
  const assert=(value,message)=>{if(!value)throw Error(message);};
  const server=()=>page.getByRole('region',{name:'Server',exact:true});
  const project=()=>page.getByRole('region',{name:'Needs you',exact:true});
  const ids=region=>region.locator('[data-home-item]').evaluateAll(ns=>ns.map(n=>n.getAttribute('data-home-item')));
  const overview=async params=>{
    const response=await page.request.get(origin+'/api/v1/home/overview?'+new URLSearchParams(params));
    assert(response.status()===200,'Canonical overview unavailable');return (await response.json()).data;
  };
  const scope=()=>page.getByRole('combobox',{name:'Workspace scope'});
  const select=async value=>{
    if(await scope().inputValue()===value){await server().waitFor();return;}
    const response=page.waitForResponse(r=>r.url().includes('/api/v1/home/overview?')&&new URL(r.url()).searchParams.get('workspace_id')===(value==='all'?null:value)&&r.status()===200);
    await scope().selectOption(value);await response;
    await server().waitFor();
  };
  const counters=()=>page.locator('[aria-label="Operational summary"]').evaluate(dl=>Object.fromEntries([...dl.children].map(div=>[div.querySelector('dt').textContent,div.querySelector('dd').textContent])));
  const run=async(name,action)=>checks.push({name,status:'PASS',detail:await action()});
  try{
    await page.setViewportSize({width:1440,height:1100});await page.reload();await server().waitFor();
    const base=await overview({workspace_id:'home-alpha'});
    assert(base.server_attention.total===6,'Six contract Server occurrences required');
    const globalIds=new Set(base.server_attention.items.map(x=>x.attention_id));
    await run('Canonical shared relation keeps Summary, page filters and Server preferences compatible',async()=>{
      const requests=[];
      const baselineResponse=await page.request.get(origin+'/api/v1/attention?state=all&seen=all&limit=200');
      assert(baselineResponse.status()===200,'Canonical unfiltered baseline failed');
      const baseline=(await baselineResponse.json()).data;
      assert(baseline.total===baseline.items.length,'Fixture baseline unexpectedly paginated');
      assert(baseline.items.filter(x=>x.source_type==='contract_probe_only').length===14,'Contract probe set must remain intact');
      for(const query of [{},{workspace_id:'home-alpha'},{workspace_id:'home-beta'},{agent_id:'not-A'},
        {category:'watch'},{kind:'runtime_recovery_attention'},{priority:'20'},{state:'expired'},{state:'all'},{seen:'seen'},{seen:'unseen'}]){
        const expectedItems=baseline.items.filter(item=>{
          for(const name of ['workspace_id','agent_id','category','kind','priority'])if(query[name]!==undefined&&String(item[name])!==query[name])return false;
          if((query.state||'active')==='active'&&!item.active)return false;
          if(query.state&& !['active','all'].includes(query.state)&&item.resolution!==query.state)return false;
          if(query.seen==='seen'&&!item.seen_state.seen||query.seen==='unseen'&&item.seen_state.seen)return false;
          return true;
        });
        const expected=expectedItems.length;
        for(const endpoint of ['summary','page']){
          const suffix=endpoint==='summary'?'/summary':'';
          const response=await page.request.get(origin+'/api/v1/attention'+suffix+'?'+new URLSearchParams({...query,...(endpoint==='page'?{limit:20}:{})}));
          assert(response.status()===200,'Canonical '+endpoint+' failed for '+JSON.stringify(query));
          const dto=(await response.json()).data;
          assert(dto.total===expected,'Canonical '+endpoint+' ignored filters '+JSON.stringify(query));
          if(endpoint==='page'){
            assert(dto.items.length===expected,'Canonical page omitted contract items');
            assert(JSON.stringify(dto.items.map(x=>x.attention_id).sort())===JSON.stringify(expectedItems.map(x=>x.attention_id).sort()),'Canonical page filtering changed identity');
            for(const item of dto.items)for(const name of ['workspace_id','agent_id','category','kind','priority'])if(query[name]!==undefined)
              assert(String(item[name])===query[name],'Canonical filter changed '+name);
          }
          requests.push({endpoint,query,total:dto.total,status:response.status()});
        }
      }
      return {baselineTotal:baseline.total,contractProbeItems:14,realRequests:requests,canonicalViews:'viewing + filtered',queryBudgetSeconds:5};
    });
    await run('Server scope remains separate from project counters and filters',async()=>{
      const summaries={};
      for(const workspace of ['home-alpha','home-beta','all']){
        await select(workspace);
        const dto=await overview(workspace==='all'?{}:{workspace_id:workspace});
        assert(dto.server_attention.total===6,'Server total changed with project');
        assert(dto.server_attention.items.every(x=>x.workspace_id===null),'Global item attributed to a project');
        assert(dto.attention.items.every(x=>x.workspace_id!==null),'Global occurrence leaked into project partition');
        const expected=workspace==='all'?8:4;
        assert(dto.summary.needs_you.value===expected,'Server attention contaminated project counter');
        assert((await counters())['Needs you']===String(expected),'Rendered Needs-you counter mixed scopes');
        assert((await ids(server())).every(id=>globalIds.has(id)),'Rendered Server identity changed with scope');
        assert((await ids(project())).every(id=>!globalIds.has(id)),'Global item rendered under project Needs you');
        summaries[workspace]=dto.summary.needs_you.value;
      }
      await select('home-alpha');
      await page.getByRole('combobox',{name:'Filter Home by agent'}).fill('not-A');
      let response=page.waitForResponse(r=>r.url().includes('/api/v1/home/overview?')&&new URL(r.url()).searchParams.get('agent_id')==='not-A');
      await page.getByRole('button',{name:'Apply agent filter',exact:true}).click();await response;
      response=page.waitForResponse(r=>r.url().includes('/api/v1/home/overview?')&&new URL(r.url()).searchParams.get('state')==='running');
      await page.getByRole('combobox',{name:'Work state'}).selectOption('running');await response;
      assert((await ids(server())).every(id=>globalIds.has(id)),'Agent/work-state filters changed Server content');
      const filtered=await overview({workspace_id:'home-alpha',agent_id:'not-A',state:'running'});
      assert(filtered.server_attention.total===6&&filtered.attention.total===0,'Filter independence failed');
      response=page.waitForResponse(r=>r.url().includes('/api/v1/home/overview?')&&!new URL(r.url()).searchParams.has('agent_id')&&!new URL(r.url()).searchParams.has('state'));
      await page.getByRole('button',{name:'Clear filters',exact:true}).click();await response;
      return {summaries,serverTotal:6,globalWorkspaceNull:true,filterIndependence:true};
    });
    await run('Project and Server pagination use independent real endpoints and canonical IDs',async()=>{
      const before=await counters();
      let response=page.waitForResponse(r=>r.url().includes('/api/v1/home/server-attention?')&&r.status()===200);
      await server().getByRole('button',{name:'Load more server',exact:true}).click();await response;
      const serverIds=await ids(server());assert(new Set(serverIds).size===6&&serverIds.length===6,'Server paging dropped or duplicated IDs');
      response=page.waitForResponse(r=>r.url().includes('/api/v1/home/attention?')&&r.status()===200);
      await project().getByRole('button',{name:'Load more needs you',exact:true}).click();await response;
      const projectIds=await ids(project());assert(new Set(projectIds).size===4&&projectIds.length===4,'Project paging dropped or duplicated IDs');
      assert(projectIds.every(id=>!serverIds.includes(id)),'Partition cursors merged scopes');
      assert(JSON.stringify(await counters())===JSON.stringify(before),'Server pagination altered project counters');
      return {serverIds,projectIds,countersUnchanged:true};
    });
    await run('Real canonical seen CAS changes only the selected Server occurrence; pause fences controls',async()=>{
      const before=await overview({workspace_id:'home-alpha'}),item=before.server_attention.items[0];
      const row=server().locator(`[data-home-item="${item.attention_id}"]`);
      const post=page.waitForResponse(r=>new URL(r.url()).pathname===`/api/v1/attention/${item.attention_id}/seen`&&r.request().method()==='POST');
      await row.getByRole('button',{name:'Mark seen',exact:true}).click();const response=await post;
      assert(response.status()===200,'Canonical seen write failed');
      const actual=response.request().postDataJSON();
      assert(actual.source_revision===item.source_revision&&actual.preference_revision===item.seen_state.revision&&actual.seen===true,'Viewing CAS target changed');
      await row.getByRole('button',{name:'Mark unseen',exact:true}).waitFor();
      const after=await overview({workspace_id:'home-alpha'}),changed=after.server_attention.items.find(x=>x.attention_id===item.attention_id);
      assert(changed.seen_state.seen&&changed.seen_state.revision===item.seen_state.revision+1,'Canonical preference not projected');
      for(const section of ['work','results','attention'])for(const key of ['items','total','total_is_exact','revision','has_more','next_cursor'])
        assert(JSON.stringify(before[section][key])===JSON.stringify(after[section][key]),'Server viewing write changed project '+section+'.'+key);
      await page.getByRole('button',{name:'Pause display',exact:true}).click();
      assert(await row.getByRole('button',{name:'Mark unseen',exact:true}).isDisabled(),'Paused Server preference remained enabled');
      const conflict=await page.request.post(origin+`/api/v1/attention/${item.attention_id}/seen`,{headers:{'x-nexus-ui':'1'},data:{seen:false,source_revision:item.source_revision,preference_revision:item.seen_state.revision}});
      directHttpProbes.push({method:'POST',path:`/api/v1/attention/${item.attention_id}/seen`,expected:'stale captured CAS',status:conflict.status()});
      assert(conflict.status()===409,'Old canonical viewing CAS did not conflict');
      await page.getByRole('button',{name:'Resume display',exact:true}).click();
      return {attentionId:item.attention_id,sourceRevision:item.source_revision,preferenceRevisionBefore:item.seen_state.revision,preferenceRevisionAfter:changed.seen_state.revision,seenPostStatus:response.status(),oldCasStatus:conflict.status(),projectSectionsUnchanged:true,pauseDisabled:true};
    });
    await run('Quiet project still exposes the independent Server lane',async()=>{
      await select('home-quiet');await page.getByRole('heading',{name:'Set up your first agent',exact:true}).waitFor();
      assert(await server().count()===1,'Quiet project hid Server lane');
      assert((await ids(server())).length===3,'Quiet project lost Server occurrence previews');
      assert(await page.locator('[aria-label="Operational summary"]').count()===0,'Quiet-project counter grid returned for Server items');
      return {quietWelcome:true,serverPreview:3,projectCounterGridAbsent:true};
    });
    await run('Server partial freshness disables its controls; current project stays usable;403 clears protected lanes',async()=>{
      await select('home-alpha');
      const partial=async route=>{const response=await route.fetch(),value=await response.json();value.data.server_attention.status='partial';value.data.server_attention.reason_code='CONTRACT_PROBE_PARTIAL';await route.fulfill({response,json:value});};
      await page.route('**/api/v1/home/overview?*',partial);
      let response=page.waitForResponse(r=>r.url().includes('/api/v1/home/overview?')&&r.status()===200);
      await page.getByRole('button',{name:'Refresh Home',exact:true}).click();await response;
      await server().getByText(/Out of date/).waitFor();
      assert(await server().getByRole('button',{name:/Mark (un)?seen/}).first().isDisabled(),'Partial Server preference enabled');
      assert(!await project().getByRole('button',{name:'Mark seen',exact:true}).first().isDisabled(),'Fresh project preference disabled by Server partial');
      await page.unroute('**/api/v1/home/overview?*',partial);
      const forbidden=route=>route.fulfill({status:403,contentType:'application/json',body:JSON.stringify({ok:false,error:{code:'PERMISSION_DENIED',message:'Own routed authorization-loss probe'}})});
      await page.route('**/api/v1/home/**',forbidden);
      response=page.waitForResponse(r=>r.url().includes('/api/v1/home/overview?')&&r.status()===403);
      await page.getByRole('button',{name:'Refresh Home',exact:true}).click();await response;
      await page.getByText('Operator access is required. Protected Home data has been cleared.',{exact:true}).waitFor();
      assert(await page.locator('[data-home-item]').count()===0,'Authorization loss retained protected items');
      await page.unroute('**/api/v1/home/**',forbidden);
      return {partialServerDisabled:true,freshProjectUsable:true,allProtectedItemsCleared:true,routedGetFaultsOnly:true};
    });
    assert(errors.length===0,'Application page error: '+errors.join(';'));
    return {status:'PASS',checks,pageMutationRequests:mutations,directHttpProbes,pageErrors:errors,bundle:await page.locator('script[src]').evaluateAll(ns=>ns.map(n=>n.getAttribute('src'))),scope:'Domain-valid pre-authorized query-port contract items; real Home SQL/HTTP and canonical preference CAS. No global producer or NULL-workspace DB row was invented.',limits:['Partial freshness and403 are routed GET-consumer fault probes. No POST success was stubbed.','No native harness, provider, credentials or production data.']};
  }finally{
    page.off('request',request);page.off('pageerror',pageError);await page.unrouteAll({behavior:'wait'});await page.goto('about:blank');
  }
}
