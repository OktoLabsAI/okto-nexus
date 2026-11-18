"""Static counterpart for a native-focusable, read-only scrollable PRE."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent;REPO=HERE.parents[3]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(HERE/'keyboard-v3.js')=='629e5071113f5495a29ba9ac469b74046faba9509d30842928a905b99cd09ecb'
text=(HERE/'keyboard-v3.js').read_text()
start=text.index('  const nameProof=');end=text.index('  const tabTo=',start)
text=text[:start]+'''  const nameProof=async locator=>{
    const ax=await locator.ariaSnapshot(),first=ax.split('\\n')[0];
    const shape=await locator.evaluate(e=>{
      const interactive=new Set(['button','link','checkbox','radio','switch','textbox','searchbox','combobox','listbox','option','slider','spinbutton','tab','menuitem','menuitemcheckbox','menuitemradio','treeitem']);
      const childAction=!!e.querySelector('button,a[href],input,select,textarea,summary,[tabindex],[contenteditable]')||Array.from(e.querySelectorAll('[role]')).some(n=>interactive.has(n.getAttribute('role')));
      const s=getComputedStyle(e);
      return {tag:e.tagName,role:e.getAttribute('role'),tabindex:e.getAttribute('tabindex'),editable:e.isContentEditable,childAction,overflowY:s.overflowY,scrollHeight:e.scrollHeight,clientHeight:e.clientHeight,insideDialog:!!e.closest('dialog[open]')};
    });
    if(shape.tag==='PRE'){
      const content=await locator.evaluate(async(e,axText)=>{
        const enc=new TextEncoder(),text=enc.encode(e.textContent??''),ax=enc.encode(axText);
        const digest=async bytes=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))).map(n=>n.toString(16).padStart(2,'0')).join('');
        return {textNonempty:!!e.textContent?.trim(),axNonempty:!!axText.trim(),textBytes:text.length,axBytes:ax.length,textSha256:await digest(text),axSha256:await digest(ax)};
      },ax);
      const parentAX=(await modal.ariaSnapshot()).split('\\n')[0];
      const parentNamed=/^- dialog "[^"\\n]+"/.test(parentAX);
      const staticScrollable=shape.role===null&&shape.tabindex===null&&!shape.editable&&!shape.childAction&&shape.insideDialog&&['auto','scroll'].includes(shape.overflowY)&&shape.scrollHeight>shape.clientHeight&&content.textNonempty&&content.axNonempty&&parentNamed;
      // Do not serialize the technical payload or CAS into the observation.
      return {named:false,staticScrollable,shape,content,parentAX};
    }
    const summary=shape.tag==='SUMMARY';
    const named=/^- [\\w-]+ "[^"\\n]+"/.test(first)||(summary&&/^- (text|generic): \\S/.test(first));
    return {ax:first,named,summaryContentName:summary,staticScrollable:false};
  };
  const scrollStaticPre=async(locator,label)=>{
    const snap=()=>locator.evaluate(e=>({top:e.scrollTop,max:e.scrollHeight-e.clientHeight,focused:document.hasFocus()&&e===document.activeElement&&e.matches(':focus'),windowY:scrollY,selectionLength:getSelection()?.toString().length??0,selectCounts:Array.from(e.closest('dialog').querySelectorAll('select')).map(n=>n.selectedOptions.length)}));
    const settle=async()=>{
      const end=Date.now()+1500;let last=null,stable=0,value;
      do{value=await snap();if(last!==null&&Math.abs(value.top-last)<.1)stable++;else stable=0;last=value.top;if(stable>=3)return value;await page.waitForTimeout(40);}while(Date.now()<end);
      return value;
    };
    const before=await settle(),writesBefore=page.__i01Writes.length;
    check(label+'-pre-scroll-precondition',before.focused&&before.top<before.max,before);
    await page.keyboard.press('ArrowDown');const down=await settle();
    check(label+'-ArrowDown-scrolls-own-pre',down.focused&&down.top>before.top&&Math.abs(down.windowY-before.windowY)<=1,{before,down});
    await page.keyboard.press('ArrowUp');const up=await settle();
    check(label+'-ArrowUp-restores-own-pre',up.focused&&up.top<down.top&&Math.abs(up.top-before.top)<=2&&Math.abs(up.windowY-before.windowY)<=1,{before,up});
    check(label+'-arrows-no-selection-or-request-write',before.selectionLength===0&&down.selectionLength===0&&up.selectionLength===0&&JSON.stringify(before.selectCounts)===JSON.stringify(down.selectCounts)&&JSON.stringify(before.selectCounts)===JSON.stringify(up.selectCounts)&&page.__i01Writes.length===writesBefore,{selectionLengths:[before.selectionLength,down.selectionLength,up.selectionLength],selectCounts:[before.selectCounts,down.selectCounts,up.selectCounts],writesBefore,writesAfter:page.__i01Writes.length});
  };
''' +text[end:]
old="""    check(label+'-ua-modal',await modal.evaluate(e=>e.matches(':modal')),true);
    const inventory=await inventoryOf(modal);"""
new="""    check(label+'-ua-modal',await modal.evaluate(e=>e.matches(':modal')),true);
    const dialogName=await nameProof(modal);check(label+'-dialog-accessible-name',dialogName.named,dialogName);
    const staticProbed=new Set();
    const inventory=await inventoryOf(modal);"""
assert text.count(old)==1;text=text.replace(old,new)
old="""f.inModal&&f.visible&&f.focusVisible&&f.paintedFocus&&n?.named)),{focus:f,name:n,outsideDocument});
      if(!outsideDocument&&!visited.includes(f.path))visited.push(f.path);"""
new="""f.inModal&&f.visible&&f.focusVisible&&f.paintedFocus&&(n?.named||n?.staticScrollable))),{focus:f,name:n,outsideDocument});
      if(n?.staticScrollable&&!staticProbed.has(f.path)){
        await scrollStaticPre(page.locator(':focus'),label+'-'+step);staticProbed.add(f.path);
      }
      if(!outsideDocument&&!visited.includes(f.path))visited.push(f.path);"""
assert text.count(old)==1;text=text.replace(old,new)
(HERE/'keyboard-v4.js').write_text(text)
runner=(HERE/'run_v3.py').read_text().replace("HERE/'prepared-keyboard-v3.json'","HERE/'prepared-keyboard-v4.json'").replace("'keyboard-v3.js'","'keyboard-v4.js'")
ast.parse(runner);(HERE/'run_v4.py').write_text(runner)
diff=''.join(difflib.unified_diff((HERE/'keyboard-v3.js').read_text().splitlines(True),text.splitlines(True),fromfile='keyboard-v3.js',tofile='keyboard-v4.js'))
diff+=''.join(difflib.unified_diff((HERE/'run_v3.py').read_text().splitlines(True),runner.splitlines(True),fromfile='run_v3.py',tofile='run_v4.py'))
(HERE/'variant-v4.diff').write_text(diff)
manifest=json.loads((HERE/'prepared-keyboard-v3.json').read_text())
for name in ['keyboard-v4.js','run_v4.py','prepare_v4.py','variant-v4.diff','variant-v4-notes.md','prepared-keyboard-v3.json']:
    p=HERE/name;manifest['input_pins'][p.relative_to(REPO).as_posix()]=sha(p)
manifest['status']='I01_STATIC_PRE_COUNTERPART_PREPARED_NOT_EXECUTED'
manifest['counterpart_changes']=['Mandatory accessible names unchanged for actionable controls and named dialog','Only implicit native-focusable PRE with no role/tabindex/editing/child action can use nonempty content hashes/byte lengths instead of control name','Painted in-modal focus and actual ArrowDown/ArrowUp own scrolling, no text/form selection/write; original partial remains']
(HERE/'prepared-keyboard-v4.json').write_text(json.dumps(manifest,indent=2)+'\n')
gate=json.loads((HERE/'GATE-v3.template.json').read_text());assert gate['approved']is False;gate['manifest_sha256']=sha(HERE/'prepared-keyboard-v4.json');gate['cut_id']='hst-native-zoom-r9-keyboard-3'
(HERE/'GATE-v4.template.json').write_text(json.dumps(gate,indent=2)+'\n')
print(json.dumps(dict(status='PREPARED_NOT_EXECUTED',manifest_sha256=sha(HERE/'prepared-keyboard-v4.json'),files={n:sha(HERE/n)for n in ['run_v4.py','keyboard-v4.js','variant-v4.diff']}),indent=2))
