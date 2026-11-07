"""Explicit synthetic-only integration; no productive campaign entry point."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile

ROOT=Path(__file__).resolve().parent
Q=Path(r'C:/Users/jpamb/AppData/Local/Temp/r3-cooperative-drain-09ucmgsr/venv').resolve()
assert Path(sys.prefix).resolve()==Q and len(sys.argv)==1
sys.path[:0]=[str(ROOT),str(ROOT/'fixtures')]
import okto_nexus, nexus_connector_core, okto_nexus_connector
modules=(okto_nexus,nexus_connector_core,okto_nexus_connector)
assert all(Path(m.__file__).resolve().is_relative_to(Q) for m in modules)
RUN=Path(tempfile.mkdtemp(prefix='synthetic-run-',dir=ROOT))
print(json.dumps({'synthetic_run':str(RUN)}),flush=True)
paths=[p for m in modules for p in Path(m.__file__).parent.rglob('*')
       if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc']
paths+=list((ROOT/'fixtures').glob('*.py'))
paths+=[ROOT/n for n in ('controller.py','setup_journal.py','test_controller.py','run_synthetic.py',
                        'response_loss.py','token_collector.py','pytest.ini','fixture-manifest.json')]
def hashes(): return {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
before=hashes()
for row in json.loads((ROOT/'fixture-manifest.json').read_text()):
    assert before[str(ROOT/'fixtures'/row['name'])]==row['sha256']
assert before[str(ROOT/'token_collector.py')]=='10584c1675b0a6cd8f586b3b62fd9694eb5c7ac0433854f991e81c8f7eb5d574'
assert before[str(ROOT/'response_loss.py')]=='90384048f66c4eded5c119d7380debf22a288ff3c03270d01714b685326b8d56'
(RUN/'input-hashes-before.json').write_text(json.dumps(before,indent=2)+'\n',encoding='utf-8')
import pytest
status=pytest.main(['-q','-c',str(ROOT/'pytest.ini'),'--confcutdir',str(ROOT),str(ROOT/'test_controller.py'),
                   '--junitxml',str(RUN/'results.xml'),'--basetemp',str(RUN/'test-state')])
after=hashes()
(RUN/'input-hashes-after.json').write_text(json.dumps(after,indent=2)+'\n',encoding='utf-8')
shadowed=[name for name,module in tuple(sys.modules.items())
          if name.split('.')[0] in {'okto_nexus','nexus_connector_core','okto_nexus_connector'}
          and getattr(module,'__file__',None) and not Path(module.__file__).resolve().is_relative_to(Q)]
result={'pytest_exit':int(status),'input_files':len(before),'inputs_unchanged':before==after,
        'shadowed_product_modules':shadowed,'scope':'Installed Core/Nexus with synthetic native; setup private journal + canonical work pages',
        'provider':False,'vault':False,'os_service':False,'connector_topology':False}
(RUN/'status.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
assert before==after and not shadowed
raise SystemExit(status)
