from pathlib import Path
import hashlib,json,sys
root=Path(__file__).parent
sys.path.insert(0,str(root))
paths=list(root.glob('*.py'))+[root/'pytest.ini']
before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
(root/'input-hashes-before.json').write_text(json.dumps(before,indent=2))
import pytest
code=pytest.main(['-q','-c',str(root/'pytest.ini'),'--confcutdir',str(root),str(root/'test_publication.py'),'--junitxml',str(root/'results.xml')])
after={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
(root/'input-hashes-after.json').write_text(json.dumps(after,indent=2))
(root/'status.json').write_text(json.dumps({'pytest_exit':int(code),'inputs_unchanged':before==after,
    'scope':'Pure simulated diagnostic publication; prepared runner not executed; no provider/HTTP/CLI/service/vault.'},indent=2))
assert before==after
raise SystemExit(code)
