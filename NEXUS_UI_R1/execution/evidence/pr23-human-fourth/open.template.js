async page=>{
 const cfg=__CFG__;
 await page.addInitScript(()=>{
  if(location.protocol==='http:'){
   localStorage.setItem('okto-nexus-home-operational','enabled');localStorage.setItem('okto-nexus-workspace','ws');
   localStorage.setItem('okto.nexus.onboarding.completed.v1','true');localStorage.setItem('okto-nexus:metrics-opt-in-prompt-dismissed:1.0.0','test');
   document.addEventListener('click',event=>{if(!event.isTrusted)return;const control=event.target.closest('button,summary,[role="button"]');if(!control)return;const label=(control.getAttribute('aria-label')||control.textContent||'').trim().slice(0,120);fetch('/__ui043/action?label='+encodeURIComponent(label),{cache:'no-store'}).catch(()=>{});},true);
  }
 });
 await page.setViewportSize({width:1440,height:1000});await page.goto(cfg.url);
 await page.getByTestId('home-board').waitFor();
 const selected=await page.getByTestId('home-project-card').getByRole('combobox',{name:'Project',exact:true}).inputValue();
 const columns=await page.locator('[data-home-column]').evaluateAll(ns=>ns.map(n=>n.dataset.homeColumn));
 if(selected!=='ws'||JSON.stringify(columns)!==JSON.stringify(['active','needs_you','results']))throw Error('Initial Home scope/columns mismatch');
 await page.screenshot({path:cfg.out+'/initial-home.png',fullPage:false});
 return{status:'INITIAL_VIEW_READY_NOT_A_HUMAN_OUTCOME',url:page.url(),selected,columns,dialogs:await page.getByRole('dialog').count(),tasks_performed:false};
}
