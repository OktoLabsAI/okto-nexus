async page=>{
 const cfg={"window": "REMAINING_FUNCTIONAL_WINDOW_OPEN", "url": "http://127.0.0.1:49961", "workspace_id": "wsr_224ac397cb6e67caa17c8c657ea2f6a7", "card_id": "home_group_7dfe421cba80e46ce23a6c8ca1bd37930a70ce8cf61801f709fd9e69ea98ae2e"};if(cfg.window!=='REMAINING_FUNCTIONAL_WINDOW_OPEN')throw Error('Root review/window required');
 await page.locator('[data-home-harness="'+cfg.card_id+'"]').waitFor({timeout:10000});
 await page.getByRole('button',{name:'Ask for work or chat',exact:true}).waitFor({timeout:10000});
 const project=await page.getByRole('combobox',{name:'Project',exact:true}).inputValue();
 if(project!==cfg.workspace_id||await page.getByRole('dialog').count())return {status:'FAIL_OR_INCOMPLETE',reason:'Own project/root view not ready'};
 return {status:'READY_FOR_FRESH_QUESTIONS',workspace_id:project,dialogs:0,limits:['No native question has yet been published']};
}
