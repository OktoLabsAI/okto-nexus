"""Create only a new G01 oracle counterpart; no application/browser execution."""
import hashlib
import json
from pathlib import Path
import subprocess

HERE=Path(__file__).resolve().parent
original=(HERE/'browser.js').read_bytes()
assert hashlib.sha256(original).hexdigest()=='fb759979aa6a8fe17d1f564058f2897bb043621a30bcf6335f58d6f2dba62f85'
old="""      await open(cfg.bCard);
      const select=modal.getByLabel('Choose a session',{exact:true});
      await select.waitFor();
      await page.waitForFunction(({k})=>document.querySelector('dialog[open] select')?.value===k,{k:key(cfg.b1)});
      check('G01-unique-complete-session-selected',await select.inputValue()===key(cfg.b1),{session:cfg.b1.scope.session_id});
      await modal.getByText(cfg.b1.marker,{exact:false}).first().waitFor({timeout:12000});
      check('G01-one-modal-one-gesture-exact-output',await modal.count()===1,true);await close();"""
new="""      // Attach before the single gesture: singleton opens a target, not a chooser.
      const sessionRead=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/runtime-management/runtime/sessions/'+cfg.b1.scope.session_id&&r.request().method()==='GET',{timeout:15000});
      await open(cfg.bCard);
      const response=await sessionRead;const raw=await response.json();const body=raw.data??raw;
      const scopeKeys=Object.keys(cfg.b1.scope).sort();
      check('G01-real-canonical-GET-entire-scope',response.status()===200&&!!body.scope&&scopeKeys.every(k=>body.scope[k]===cfg.b1.scope[k]),{status:response.status(),expectedScope:cfg.b1.scope,actualScope:body.scope,comparedKeys:scopeKeys});
      const target=JSON.parse(new URL(page.url()).searchParams.get('home_target')||'null');
      check('G01-exact-target-not-latest',target?.kind==='session'&&['server_id','executor_id','workspace_id','session_id'].every(k=>target[k]===cfg.b1.scope[k]),target);
      await modal.getByText(cfg.b1.marker,{exact:false}).first().waitFor({timeout:12000});
      check('G01-one-modal-one-gesture-exact-output',await modal.count()===1,{marker:cfg.b1.marker,chooserNotRequired:true});await close();"""
source=original.decode().replace('\r\n','\n');assert source.count(old)==1
target=HERE/'browser-g01-exact.js';assert not target.exists()
target.write_text(source.replace(old,new),encoding='utf-8')
checked=subprocess.run([r'C:/Program Files/nodejs/node.exe','--check',str(target)],capture_output=True,text=True,timeout=10)
assert checked.returncode==0,checked.stderr
proof=dict(status='PREPARED_NOT_EXECUTED',original_sha256=hashlib.sha256(original).hexdigest(),variant_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),node_syntax_exit=checked.returncode,change='Only G01 singleton oracle: observe canonical GET before gesture; compare entire RuntimeSession.scope, exact URL target and actual output. No chooser assumption.',prior_failure='experience-r8-first-oracle/qualification.json')
(HERE/'g01-variant-proof.json').write_text(json.dumps(proof,indent=2)+'\n')
print(json.dumps(proof,indent=2))
