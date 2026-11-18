"""Static coverage counterpart; preserves the first prepared keyboard manifest."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent;REPO=HERE.parents[3]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(HERE/'keyboard.js')=='9ee6a4952a031ad9d8e74e8b95e1746890dd54d81a661b4e50157ff1e974754d'
text=(HERE/'keyboard.js').read_text()
start=text.index('  const modalCycle=')
end=text.index('  const escape=',start)
text=text[:start]+'''  const sequential='button,a[href],input:not([type=hidden]),select,textarea,summary,[tabindex]';
  const inventoryOf=async scope=>scope.locator(sequential).evaluateAll((nodes,fn)=>{const path=Function('return ('+fn+')')();return nodes.filter(e=>e.tabIndex>=0&&!e.disabled&&e.getBoundingClientRect().width>0&&e.getBoundingClientRect().height>0&&getComputedStyle(e).visibility!=='hidden'&&!e.closest('[inert]')).map(e=>path(e));},String(pathOf));
  const modalCycle=async label=>{
    check(label+'-ua-modal',await modal.evaluate(e=>e.matches(':modal')),true);
    const inventory=await inventoryOf(modal);check(label+'-modal-controls-nonempty',inventory.length>0,inventory.length);
    const visited=[],cycle=[];
    for(let i=0;i<90&&!inventory.every(p=>visited.includes(p));i++){
      await page.keyboard.press('Tab');
      check(label+'-focused-element-present-'+i,await page.locator(':focus').count()===1,true);
      const f=await focused(),n=await nameProof(page.locator(':focus'));
      check(label+'-contained-'+i,f.inModal&&f.visible&&f.focusVisible&&f.paintedFocus&&n.named,{focus:f,name:n});
      if(visited.includes(f.path)&&!inventory.every(p=>visited.includes(p)))break;
      visited.push(f.path);cycle.push({focus:f,name:n});
    }
    check(label+'-all-enabled-modal-controls-covered',inventory.every(p=>visited.includes(p)),{inventory,visited,missing:inventory.filter(p=>!visited.includes(p)),cycle});
    // Cross both ends with benign keys only; never activate Copy/submit/decision.
    for(const key of ['Tab','Shift+Tab']){
      await page.keyboard.press(key);const f=await focused();
      check(label+'-boundary-contained-'+key,f.inModal&&f.visible&&f.focusVisible&&f.paintedFocus,f);
    }
  };
''' +text[end:]
old="""      const selector='button,a[href],input:not([type=hidden]),select,textarea,summary,[tabindex]';
      const inventory=await page.locator(selector).evaluateAll((nodes,fn)=>{const path=Function('return ('+fn+')')();return nodes.filter(e=>e.tabIndex>=0&&!e.disabled&&e.getBoundingClientRect().width>0&&e.getBoundingClientRect().height>0&&getComputedStyle(e).visibility!=='hidden'&&!e.closest('[inert]')).map(e=>path(e));},String(pathOf));"""
assert text.count(old)==1;text=text.replace(old,"      const inventory=await inventoryOf(page);")
old="""      let first=null,visited=[];
      for(let i=0;i<220;i++){
        await page.keyboard.press('Tab');const f=await focused(),n=await nameProof(page.locator(':focus'));
        if(first===f.path)break;
        if(first===null)first=f.path;
        check('home-control-named-focus-'+i,n.named&&f.visible&&f.focusVisible&&f.paintedFocus,{focus:f,name:n});visited.push(f.path);records.push({phase:'home-inventory',focus:f,name:n});
      }
      check('full-home-keyboard-cycle-covers-all-actionable',inventory.every(p=>visited.includes(p)),{inventory,visited,missing:inventory.filter(p=>!visited.includes(p))});"""
new="""      const visited=[];let boundary=null;
      for(let i=0;i<220&&!inventory.every(p=>visited.includes(p));i++){
        await page.keyboard.press('Tab');
        if(await page.locator(':focus').count()!==1){boundary='No focused page element before coverage';break;}
        const f=await focused(),n=await nameProof(page.locator(':focus'));
        check('home-control-named-focus-'+i,n.named&&f.visible&&f.focusVisible&&f.paintedFocus,{focus:f,name:n});
        if(visited.includes(f.path)){boundary='Focus repeated before inventory coverage';break;}
        visited.push(f.path);records.push({phase:'home-inventory',focus:f,name:n});
      }
      check('full-home-keyboard-covers-all-actionable',inventory.every(p=>visited.includes(p)),{inventory,visited,missing:inventory.filter(p=>!visited.includes(p)),boundary});"""
assert text.count(old)==1;text=text.replace(old,new)
old="""      check('request-original-unanswered',await input.evaluate(e=>e.selectedOptions.length===0),{requestId:cfg.requestId,session:cfg.a2Scope.session_id});
      await modalCycle('needs-you');"""
new="""      check('request-original-unanswered',await input.evaluate(e=>e.selectedOptions.length===0),{requestId:cfg.requestId,session:cfg.a2Scope.session_id});
      const deny=decision.getByRole('button',{name:'Deny runtime request',exact:true});await deny.waitFor();
      const readyDeadline=Math.min(Date.now()+12000,Date.parse(cfg.expiresAt));
      while(!await deny.isEnabled()&&Date.now()<readyDeadline)await page.waitForTimeout(50);
      check('canonical-request-controls-ready-before-inventory',await deny.isEnabled(),{session:cfg.a2Scope.session_id});
      await modalCycle('needs-you');"""
assert text.count(old)==1;text=text.replace(old,new)
(HERE/'keyboard-v2.js').write_text(text)
runner=(HERE/'run.py').read_text().replace("HERE/'prepared-keyboard.json'","HERE/'prepared-keyboard-v2.json'").replace("'keyboard.js'","'keyboard-v2.js'")
ast.parse(runner);(HERE/'run_v2.py').write_text(runner)
diff=''.join(difflib.unified_diff((HERE/'keyboard.js').read_text().splitlines(True),text.splitlines(True),fromfile='keyboard.js',tofile='keyboard-v2.js'))
diff+=''.join(difflib.unified_diff((HERE/'run.py').read_text().splitlines(True),runner.splitlines(True),fromfile='run.py',tofile='run_v2.py'))
(HERE/'variant-v2.diff').write_text(diff)
manifest=json.loads((HERE/'prepared-keyboard.json').read_text())
for name in ['keyboard-v2.js','run_v2.py','prepare_v2.py','variant-v2.diff','variant-v2-notes.md','prepared-keyboard.json']:
    p=HERE/name;manifest['input_pins'][p.relative_to(REPO).as_posix()]=sha(p)
manifest['status']='I01_KEYBOARD_COVERAGE_COUNTERPART_PREPARED_NOT_EXECUTED'
manifest['counterpart_changes']=['Stop Home tab collection immediately when every inventoried control is visited; missing/trapped controls still fail','Modal inventory coverage and boundary containment; await canonical listbox plus enabled Deny before request inventory; no action activation']
(HERE/'prepared-keyboard-v2.json').write_text(json.dumps(manifest,indent=2)+'\n')
gate=json.loads((HERE/'GATE.template.json').read_text());assert gate['approved']is False;gate['manifest_sha256']=sha(HERE/'prepared-keyboard-v2.json')
(HERE/'GATE-v2.template.json').write_text(json.dumps(gate,indent=2)+'\n')
print(json.dumps(dict(status='PREPARED_NOT_EXECUTED',manifest_sha256=sha(HERE/'prepared-keyboard-v2.json'),files={n:sha(HERE/n)for n in ['run_v2.py','keyboard-v2.js','variant-v2.diff']}),indent=2))
