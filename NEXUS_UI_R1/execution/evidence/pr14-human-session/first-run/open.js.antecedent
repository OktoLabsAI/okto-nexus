async page=>{
 await page.addInitScript(()=>{if(location.protocol!=='http:')return;localStorage.setItem('okto-nexus-home-operational','enabled');localStorage.setItem('okto-nexus-workspace','ws');localStorage.setItem('okto.nexus.onboarding.completed.v1','true');localStorage.setItem('okto-nexus:metrics-opt-in-prompt-dismissed:1.0.0','test');
  document.addEventListener('click',event=>{const element=event.target instanceof Element?event.target.closest('button,a,summary'):null;if(!element)return;const label=(element.getAttribute('aria-label')||element.textContent||'').trim().replace(/\s+/g,' ').slice(0,120);void fetch('/__ui043/action?label='+encodeURIComponent(label),{keepalive:true});},true);
 });
 await page.setViewportSize({width:1440,height:1000});await page.goto('http://127.0.0.1:61381');await page.getByTestId('home-follow-up').waitFor();return{url:page.url(),title:await page.title(),heading:await page.getByRole('heading',{name:'Home',exact:true}).innerText(),dialogs:await page.getByRole('dialog').count()};
}
