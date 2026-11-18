"""Static native-dialog-aware observation counterpart; no runtime."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent;REPO=HERE.parents[3]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(HERE/'keyboard-v2.js')=='b08720a4db172172da57fc0d48122bf7c6509f7f9a6b386d93e5a9410fe68d92'
text=(HERE/'keyboard-v2.js').read_text()
start=text.index('  const focused=');end=text.index('  const nameProof=',start)
text=text[:start]+'''  const focused=async()=>{
    const f=await page.evaluate(fn=>{
      const e=document.activeElement,d=document.querySelector('dialog[open]'),path=Function('return ('+fn+')')(),s=e?getComputedStyle(e):null,r=e?.getBoundingClientRect();
      return {path:e?path(e):null,tag:e?.tagName,type:e?.getAttribute('type'),hasFocus:document.hasFocus(),focusCountDOM:document.querySelectorAll(':focus').length,activeMatchesFocus:e?.matches(':focus'),modalOpen:!!d,uaModal:!!d?.matches(':modal'),focusVisible:e?.matches(':focus-visible'),paintedFocus:s?((s.outlineStyle!=='none'&&parseFloat(s.outlineWidth)>0)||s.boxShadow!=='none'):false,outline:s?.outlineStyle,outlineWidth:s?.outlineWidth,shadow:s?.boxShadow,visible:!!r&&r.width>0&&r.height>0,inModal:!!e?.closest('dialog[open]'),homeId:e?.closest('[data-home-harness],[data-home-signal]')?.getAttribute('data-home-harness')||e?.closest('[data-home-signal]')?.getAttribute('data-home-signal'),focusEvents:(window.__i01FocusEvents??[]).splice(0)};
    },String(pathOf));
    f.focusCountLocator=await page.locator(':focus').count();return f;
  };
''' +text[end:]
start=text.index('  const modalCycle=');end=text.index('  const escape=',start)
text=text[:start]+'''  const modalCycle=async label=>{
    check(label+'-ua-modal',await modal.evaluate(e=>e.matches(':modal')),true);
    const inventory=await inventoryOf(modal);check(label+'-modal-controls-nonempty',inventory.length>0,inventory.length);
    const visited=[],cycle=[];
    const observe=async step=>{
      const f=await focused();let n=null;
      if(f.hasFocus&&f.activeMatchesFocus&&f.focusCountDOM===1&&f.focusCountLocator===1)n=await nameProof(page.locator(':focus'));
      const outsideDocument=f.hasFocus===false&&f.focusCountDOM===0&&f.focusCountLocator===0&&f.activeMatchesFocus===false&&f.modalOpen&&f.uaModal;
      records.push({phase:label,step,focus:f,name:n,outsideDocument});cycle.push({step,focus:f,name:n,outsideDocument});
      check(label+'-no-background-focus-event-'+step,!f.focusEvents.some(e=>e.event==='focusin'&&e.modalOpen&&!e.targetInModal),f.focusEvents);
      check(label+'-native-modal-focus-state-'+step,f.modalOpen&&f.uaModal&&(outsideDocument||(f.hasFocus&&f.activeMatchesFocus&&f.focusCountDOM===1&&f.focusCountLocator===1&&f.inModal&&f.visible&&f.focusVisible&&f.paintedFocus&&n?.named)),{focus:f,name:n,outsideDocument});
      if(!outsideDocument&&!visited.includes(f.path))visited.push(f.path);
      return {f,outsideDocument};
    };
    // Count the actual initial focus rather than Tab past the first control.
    await observe('initial');
    for(let i=0;i<90&&!inventory.every(p=>visited.includes(p));i++){
      await page.keyboard.press('Tab');await observe('Tab-'+i);
    }
    check(label+'-all-enabled-modal-controls-covered',inventory.every(p=>visited.includes(p)),{inventory,visited,missing:inventory.filter(p=>!visited.includes(p)),cycle});
    for(const key of ['Tab','Shift+Tab']){
      await page.keyboard.press(key);let state=await observe('boundary-'+key);
      // Bounded benign navigation can return from browser-level focus; never focus() or trap.
      for(let i=0;i<6&&state.outsideDocument;i++){
        await page.keyboard.press(key);state=await observe('return-'+key+'-'+i);
      }
      check(label+'-returned-to-dialog-'+key,!state.outsideDocument&&state.f.inModal,state.f);
    }
  };
''' +text[end:]
old="""      await page.addInitScript(origin=>{if(location.origin!==origin)return;localStorage.setItem('okto-nexus-home-operational','enabled');localStorage.setItem('okto-nexus-workspace','all');localStorage.setItem('okto-nexus:metrics-opt-in-prompt-dismissed:1.0.0',new Date().toISOString());},new URL(cfg.url).origin);"""
new="""      await page.addInitScript(origin=>{
        if(location.origin!==origin)return;
        localStorage.setItem('okto-nexus-home-operational','enabled');localStorage.setItem('okto-nexus-workspace','all');localStorage.setItem('okto-nexus:metrics-opt-in-prompt-dismissed:1.0.0',new Date().toISOString());
        window.__i01FocusEvents=[];
        const capture=(event,target)=>{
          const d=document.querySelector('dialog[open]'),e=document.activeElement;
          window.__i01FocusEvents.push({event,time:performance.now(),hasFocus:document.hasFocus(),focusCountDOM:document.querySelectorAll(':focus').length,activeTag:e?.tagName,activeMatchesFocus:e?.matches(':focus'),modalOpen:!!d,uaModal:!!d?.matches(':modal'),targetTag:target?.tagName??null,targetInModal:!!target?.closest?.('dialog[open]')});
        };
        for(const name of ['focusin','focusout','focus','blur'])document.addEventListener(name,event=>capture(name,event.target),true);
        for(const name of ['focus','blur'])window.addEventListener(name,()=>capture('window-'+name,null));
      },new URL(cfg.url).origin);"""
assert text.count(old)==1;text=text.replace(old,new)
text=text.replace("'No AT speech/theme claim'","'No AT speech/theme claim'")
(HERE/'keyboard-v3.js').write_text(text)
runner=(HERE/'run_v2.py').read_text().replace("HERE/'prepared-keyboard-v2.json'","HERE/'prepared-keyboard-v3.json'").replace("'keyboard-v2.js'","'keyboard-v3.js'")
ast.parse(runner);(HERE/'run_v3.py').write_text(runner)
diff=''.join(difflib.unified_diff((HERE/'keyboard-v2.js').read_text().splitlines(True),text.splitlines(True),fromfile='keyboard-v2.js',tofile='keyboard-v3.js'))
diff+=''.join(difflib.unified_diff((HERE/'run_v2.py').read_text().splitlines(True),runner.splitlines(True),fromfile='run_v2.py',tofile='run_v3.py'))
(HERE/'variant-v3.diff').write_text(diff)
manifest=json.loads((HERE/'prepared-keyboard-v2.json').read_text())
for name in ['keyboard-v3.js','run_v3.py','prepare_v3.py','variant-v3.diff','variant-v3-notes.md','prepared-keyboard-v2.json']:
    p=HERE/name;manifest['input_pins'][p.relative_to(REPO).as_posix()]=sha(p)
manifest['status']='I01_NATIVE_MODAL_OBSERVATION_COUNTERPART_PREPARED_NOT_EXECUTED'
manifest['counterpart_changes']=['Count and validate actual initial modal focus','Serialize initial/boundary DOM and locator focus counts, hasFocus, active element, UA modal, focus events and styles','Accept only explicit zero-page-focus outside-document states; bounded Tab/ShiftTab returns; actual background page focus or focusin is failure','Same three exact targets and Escape/focus return; no product trap or decision']
(HERE/'prepared-keyboard-v3.json').write_text(json.dumps(manifest,indent=2)+'\n')
gate=json.loads((HERE/'GATE-v2.template.json').read_text());assert gate['approved']is False;gate['manifest_sha256']=sha(HERE/'prepared-keyboard-v3.json');gate['cut_id']='hst-native-zoom-r9-keyboard-2'
(HERE/'GATE-v3.template.json').write_text(json.dumps(gate,indent=2)+'\n')
print(json.dumps(dict(status='PREPARED_NOT_EXECUTED',manifest_sha256=sha(HERE/'prepared-keyboard-v3.json'),files={n:sha(HERE/n)for n in ['run_v3.py','keyboard-v3.js','variant-v3.diff']}),indent=2))
