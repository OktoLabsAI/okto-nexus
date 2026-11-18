"""Only rename the CLI launch artifact; preserve every browser phase/predicate."""
import ast
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
original=(HERE/'run_focus_return.py').read_bytes()
assert hashlib.sha256(original).hexdigest()=='696e30519aef62822f108f38bc043ce008a0f4b03e1ebe61cf4c6c09e8b07b57'
source=original.decode().replace('\r\n','\n')
needle="exec(compile(source,str(HERE/'run.py'),'exec'))"
replacement="""assert source.count("cli('open','open',")==1
source=source.replace("cli('open','open',","cli('launch','open',")
exec(compile(source,str(HERE/'run.py'),'exec'))"""
assert source.count(needle)==1
prepared=source.replace(needle,replacement);ast.parse(prepared)
target=HERE/'run_focus_return_launch.py';assert not target.exists();target.write_text(prepared,encoding='utf-8')
# Parse generated original runner, but do not execute it or allocate anything.
static=prepared.replace(needle,'ast.parse(source)')
exec(compile(static,str(target),'exec'),{'__file__':str(target),'ast':ast})
proof=dict(status='PREPARED_NOT_EXECUTED',original_sha256=hashlib.sha256(original).hexdigest(),variant_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),change="Only generated runner CLI artifact name cli('open','open',...) becomes cli('launch','open',...); browser phase open unchanged",wrapper_ast='PASS',generated_runner_ast='PASS',browser_sha256=hashlib.sha256((HERE/'focus-return.js').read_bytes()).hexdigest())
(HERE/'focus-launch-proof.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof,indent=2))
