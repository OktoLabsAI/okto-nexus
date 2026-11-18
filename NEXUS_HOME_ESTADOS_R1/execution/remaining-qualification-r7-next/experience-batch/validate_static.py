"""Parse new scripts/derivatives only. Never imports product or allocates runtime."""
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess

HERE=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
for name in ['builder.py','run.py','validate_static.py']:ast.parse((HERE/name).read_text(),filename=name)
spec=importlib.util.spec_from_file_location('prepared_experience_builder',HERE/'builder.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
original=(m.BASE/'fixture.py').read_bytes()
derivatives=[]
for naming in [True,False]:
    text=m.render(original,naming_only=naming);ast.parse(text,filename='private-fixture-derivative.py')
    derivatives.append(dict(naming_only=naming,ast='PASS',lf_rendered_sha256=hashlib.sha256(text.encode()).hexdigest()))
node=subprocess.run([r'C:/Program Files/nodejs/node.exe','--check',str(HERE/'browser.js')],capture_output=True,text=True,timeout=10)
assert node.returncode==0,node.stderr
result=dict(status='STATIC_ONLY_PREPARED',runtime_started=False,product_imported=False,tests_executed=False,node_syntax_exit=node.returncode,python_ast='PASS',derivatives=derivatives,original_fixture_sha256=sha(m.BASE/'fixture.py'),files={p.name:dict(bytes=p.stat().st_size,sha256=sha(p))for p in sorted(HERE.iterdir())if p.is_file()and p.name not in ['static-validation.json','manifest.json']})
(HERE/'static-validation.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result,indent=2))
