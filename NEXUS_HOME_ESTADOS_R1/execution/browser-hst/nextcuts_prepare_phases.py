"""Static generation only; no app imports, allocation or browser invocation."""
from pathlib import Path
HERE=Path(__file__).resolve().parent
t=(HERE/'nextcuts-context-finish.js').read_text(encoding='utf-8')
prefix=t.split('  await page.reload',1)[0]
prefix='\n'.join(line for line in prefix.splitlines()if "page.on('dialog'"not in line)
tail="\n  return {status:'PASS_F05_HISTORY_READY',checks,reads,posts,historyTarget:target};\n }catch(error){return {status:'FAIL_OR_INCOMPLETE',error:String(error),checks,reads,posts};}\n}\n"
(HERE/'nextcuts-context-page.js').write_text(prefix+tail,encoding='utf-8')
part=t[t.index("  check('original-question-still-within-expiry'"):t.index("  check('zero-ui-posts'")]
part=part.replace("page.getByRole('combobox',{name:'Project',exact:true})", "page.locator('select[aria-label=\"Project\"]')")
start="""async page=>{const cfg=__CONFIG__,checks=[],posts=[];if(cfg.window!=='POST_PERF_BROWSER_WINDOW_OPEN')throw Error('Window required');const check=(id,ok,detail)=>{checks.push({id,ok,detail});if(!ok)throw Error(id);};page.on('request',r=>{if(r.method()!=='GET')posts.push({method:r.method(),path:new URL(r.url()).pathname});});try{const dialog=page.getByRole('dialog',{name:'Activity detail'});await dialog.getByRole('button',{name:'Close modal',exact:true}).click();await dialog.waitFor({state:'hidden'});
"""
end="""check('zero-ui-posts',posts.length===0,posts);return {status:'PASS_BROWSER_SUBSET',checks,posts,limits:['Project selector is inert while modal is open; actual switch follows explicit Escape discard','No native decision or provider']};}catch(error){return {status:'FAIL_OR_INCOMPLETE',error:String(error),checks,posts};}}
"""
(HERE/'nextcuts-dirty.js').write_text(start+part+end,encoding='utf-8')
print('Static phase files generated')
