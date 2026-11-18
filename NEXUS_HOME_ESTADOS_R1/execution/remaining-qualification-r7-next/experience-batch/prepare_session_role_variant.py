"""Only replace session chooser locators with the actually captured AX role/name."""
import hashlib
import json
from pathlib import Path
import subprocess

HERE=Path(__file__).resolve().parent
original=(HERE/'browser-g02-apply.js').read_bytes()
assert hashlib.sha256(original).hexdigest()=='4f4d145ecd1472637e7499ea8099783041f4bb01af94ca523d19113596460708'
old="getByLabel('Choose a session',{exact:true})";new="getByRole('combobox',{name:'Choose a session',exact:true})"
source=original.decode().replace('\r\n','\n');count=source.count(old);assert count==3
target=HERE/'browser-session-role.js';assert not target.exists();target.write_text(source.replace(old,new),encoding='utf-8')
checked=subprocess.run([r'C:/Program Files/nodejs/node.exe','--check',str(target)],capture_output=True,text=True,timeout=10);assert checked.returncode==0,checked.stderr
proof=dict(status='PREPARED_NOT_EXECUTED',changes=count,old_locator=old,new_locator=new,original_sha256=hashlib.sha256(original).hexdigest(),variant_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),node_syntax_exit=checked.returncode)
(HERE/'session-role-variant-proof.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof,indent=2))
