// Playwright CLI run-code --filename <this-file>. Run only against the finite
// browser_project_connect_fixture.py, after its Codex + Claude journey.
async (page) => {
  const origin=new URL(page.url()).origin;
  const state=async()=>await(await page.request.get(origin+'/_ui039/state')).json();
  const require=(value,message)=>{if(!value)throw new Error(message);};
  await state(); // Reject a different surface before any reviewed setup action.
  await page.reload();
  const metrics=page.getByRole('button',{name:'Close metrics settings'});
  if(await metrics.isVisible())await metrics.click();
  await page.getByRole('combobox',{name:'Workspace scope'}).selectOption({label:'UI039 project'});
  const exactWorkspace=await page.getByRole('combobox',{name:'Workspace scope'}).inputValue();
  await page.getByRole('button',{name:'Connect agent',exact:true}).click();
  await page.getByRole('button',{name:'Add another harness on this Server'}).click();
  await page.getByRole('radio',{name:'Claude Code (stream) Installation verified',exact:true}).check();
  const name=page.getByRole('textbox',{name:'Collaborator name'});
  await name.fill('UI039 reviewed collaborator');await name.press('Tab');
  require(await name.inputValue()==='UI039 reviewed collaborator','Collaborator name did not retain the typed value');
  const projectName=page.getByRole('textbox',{name:'Project name',exact:true});
  await projectName.fill('UI039 reviewed project');await projectName.press('Tab');
  require(await projectName.inputValue()==='UI039 reviewed project','Project label did not retain the typed value');
  const root=page.getByRole('textbox',{name:'Project folder on the Nexus Server'});
  const exactRoot=await root.inputValue();
  await root.fill(exactRoot+'/');await root.press('Tab');
  require(await root.inputValue()===exactRoot+'/','Project root did not retain the typed value');
  await root.fill(exactRoot);await root.press('Tab');
  await page.getByRole('button',{name:'Customize',exact:true}).click();
  await page.getByRole('textbox',{name:'Provider login directory on the Server'}).fill('');
  // Let the normal controlled input reflect the edit before the next user action.
  await page.getByRole('textbox',{name:'Provider login directory on the Server'}).press('Tab');
  require(await page.getByRole('textbox',{name:'Provider login directory on the Server'}).inputValue()==='','Provider home did not retain the cleared value');
  await page.getByRole('combobox',{name:'Nexus tool access'}).selectOption('always_allow');
  require(await page.getByRole('combobox',{name:'Nexus tool access'}).inputValue()==='always_allow','Tool access did not retain the selection');
  await page.getByRole('combobox',{name:'Nexus tool access'}).selectOption('ask');
  await page.getByRole('button',{name:'Review this connection'}).click();
  await page.getByRole('heading',{name:'Review before any model test'}).waitFor({timeout:10000});
  const review=await page.getByRole('region',{name:'Exact connection review'}).innerText();
  const reviewHost=review.match(/Server execution host\n([^\n]+)/)?.[1];
  require(!!reviewHost,'Review host label absent');
  require(review.includes('UI039 reviewed collaborator')&&review.includes('UI039 reviewed project')&&review.includes(exactRoot)&&review.includes('Harness default on the Server'),'Review did not reflect the exact typed values');
  const before=await state();
  await page.getByRole('checkbox').check();
  await page.getByRole('button',{name:'Test reviewed connection'}).click();
  await page.getByRole('button',{name:'Edit rejected review'}).waitFor({timeout:10000});
  const rejected=await state();
  const rejectedRequest=await page.evaluate(()=>JSON.parse(sessionStorage.getItem(Object.keys(sessionStorage).find(k=>k.startsWith('okto-nexus:project-connect:v1:')&&!k.includes(':previous:')))).request);
  require(JSON.stringify(rejected.counts)===JSON.stringify(before.counts),'Rejected Test changed identity/runtime counts');
  require(rejected.turns.length===before.turns.length,'Rejected Test ran a peer');
  require(rejected.calls.length===before.calls.length+1,'Rejected Test POST count is not exactly one');
  await page.screenshot({path:'output/ui039/rejection-final.png'});
  await page.reload();
  await page.getByRole('button',{name:'Connect agent',exact:true}).click();
  await page.getByRole('button',{name:'Edit rejected review'}).waitFor({timeout:10000});
  await page.getByRole('button',{name:'Edit rejected review'}).click();
  await page.getByRole('textbox',{name:'Project folder on the Nexus Server'}).waitFor({timeout:10000});
  require(await page.getByRole('combobox',{name:'Project',exact:true}).inputValue()===exactWorkspace,'Restored project picker silently displayed New project');
  require((await page.getByTestId('project-connect-flow').innerText()).includes('Execution host: '+reviewHost+'.'),'Restored executor label is absent or different');
  const edited=await state();
  require(edited.calls.length===rejected.calls.length,'Reload/edit repeated a POST');
  require(edited.turns.length===before.turns.length,'Reload/edit ran another peer');
  const retained=await page.evaluate(()=>Object.keys(sessionStorage)
    .filter(key=>key.startsWith('okto-nexus:project-connect:v1:'))
    .map(key=>({archive:key.includes(':previous:'),intent:JSON.parse(sessionStorage.getItem(key)).request?.client_intent_id,request:JSON.parse(sessionStorage.getItem(key)).request})));
  require(retained.some(item=>item.archive)&&retained.every(item=>item.archive),'Old attempt not preserved exclusively as an archive');
  require(retained[0].request.workspace_id===exactWorkspace&&JSON.stringify(retained[0].request)===JSON.stringify(rejectedRequest),'Archive changed the exact reviewed scope or configuration');
  await page.screenshot({path:'output/ui039/rejection-edited.png'});
  return {before,rejected,edited,retained,editing_did_not_submit:true};
}
