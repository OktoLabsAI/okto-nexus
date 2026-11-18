"""Fix only own CLI artifact names; browser predicate code remains byte-identical."""
import ast
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
original=(HERE/'run_focus_return_launch.py').read_bytes()
assert hashlib.sha256(original).hexdigest()=='cbf688327c566002a326ff85d4d7b3b92c2a75c5a0d10ecd9f20f1e746e33530'
source=original.decode().replace('\r\n','\n')
needle="exec(compile(source,str(HERE/'run.py'),'exec'))"
replacement="""assert source.count("cli('close','close',")==1
source=source.replace("cli('close','close',","cli('shutdown','close',")
exec(compile(source,str(HERE/'run.py'),'exec'))"""
assert source.count(needle)==1;prepared=source.replace(needle,replacement);ast.parse(prepared)
target=HERE/'run_focus_return_launch_v2.py';assert not target.exists();target.write_text(prepared,encoding='utf-8')
exec(compile(prepared.replace(needle,'ast.parse(source)'),str(target),'exec'),{'__file__':str(target),'ast':ast})
proof=dict(status='PREPARED_NOT_EXECUTED',change="Only CLI cleanup artifact cli('close','close',...) renamed cli('shutdown','close',...); JS close phase/predicates unchanged",original_sha256=hashlib.sha256(original).hexdigest(),variant_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),focus_js_sha256=hashlib.sha256((HERE/'focus-return.js').read_bytes()).hexdigest(),wrapper_and_generated_ast='PASS')
(HERE/'focus-launch-v2-proof.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof,indent=2))
