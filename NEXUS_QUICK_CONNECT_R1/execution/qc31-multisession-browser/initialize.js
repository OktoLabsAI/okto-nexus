async page=>{
 const cfg={"status": "READY_CANONICAL_MULTISESSIONS", "url": "http://127.0.0.1:57357", "reference": {"server_id": "srv_269d2c9d741d98a06c07785dbac027f6", "executor_id": "exe_296d2a3065262178625196a0f342e3cb", "binding_id": "bind_2031131ed8e50a9b2d9d0eedf0d10f56", "endpoint_id": "ep_ed874b18db791030ae811efdb070e6cc", "agent_id": "qc31-collaborator", "workspace_id": "wsr_ae4eded1d27ae3a1d28a36df18d38e38", "workspace_binding_id": "wxb_331c26efb8c44f0479b107c424299f72"}, "connect_id": "session-reviewer", "sessions": [{"label": "A", "session_id": "ses_93ddc63ff779ec4b449f1680425a99c4", "text": "QC31 Alpha retained exact output", "closed": true}, {"label": "B", "session_id": "ses_b2cee5c26f2666b0d9064363b290dcb1", "text": "QC31 Beta current exact output", "closed": false}], "provider_invocations": 0, "fake_protocol": true, "viewer_events_verified": true, "browser_readonly": true, "browser_deadline_seconds": 180, "at": "2026-11-17T10:10:16.693766+00:00"};
 await page.route('**/*',route=>['GET','HEAD','OPTIONS'].includes(route.request().method())?route.continue():route.abort());
 await page.addInitScript(()=>localStorage.setItem('okto-nexus-home-operational','enabled'));
 await page.setViewportSize({width:1440,height:1100});
 await page.goto(cfg.url,{waitUntil:'domcontentloaded'});
 await page.getByTestId('home-project-card').waitFor({timeout:15000});
 return {body:await page.locator('body').innerText()};
}
