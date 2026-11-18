async page=>{
 const cfg=__CONFIG__;if(cfg.window!=='REMAINING_FUNCTIONAL_WINDOW_OPEN')throw Error('Root review/window required');
 await page.locator('[data-home-harness="'+cfg.card_id+'"]').waitFor({timeout:10000});
 await page.getByRole('button',{name:'Ask for work or chat',exact:true}).waitFor({timeout:10000});
 const project=await page.getByRole('combobox',{name:'Project',exact:true}).inputValue();
 if(project!==cfg.workspace_id||await page.getByRole('dialog').count())return {status:'FAIL_OR_INCOMPLETE',reason:'Own project/root view not ready'};
 return {status:'READY_FOR_FRESH_QUESTIONS',workspace_id:project,dialogs:0,limits:['No native question has yet been published']};
}
