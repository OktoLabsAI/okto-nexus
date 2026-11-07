"""Remove only redundant EOF whitespace and retain exact equivalence proof."""
import ast
import hashlib
import json
from pathlib import Path
import subprocess

base = Path(__file__).parent
repo = Path(r'D:/Projetos/Techridy/okto_labs_okto_nexus')
path = repo / 'src/okto_nexus/application/remote_setup_contract.py'
before = path.read_bytes()
after = before.rstrip(b'\r\n') + b'\r\n'
assert ast.dump(ast.parse(before)) == ast.dump(ast.parse(after))
path.write_bytes(after)
proof = dict(file=str(path), before_sha256=hashlib.sha256(before).hexdigest(),
    after_sha256=hashlib.sha256(after).hexdigest(), syntax_tree_unchanged=True,
    change='Remove two redundant CRLFs at EOF; no executable syntax change')
(base / 'product-format-equivalence.json').write_text(json.dumps(proof, indent=2))
(base / 'nexus-final-nodes.json').write_text(json.dumps([
    'test_remote_setup_server.py', 'test_remote_setup_http.py', 'test_remote_setup_guards.py']))
subprocess.run(['git', 'add', '--', str(path)], cwd=repo, check=True)
subprocess.run(['git', 'diff', '--cached', '--check'], cwd=repo, check=True)
print(json.dumps(proof))
