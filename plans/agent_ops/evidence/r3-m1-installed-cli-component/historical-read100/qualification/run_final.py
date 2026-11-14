"""One isolated installed-package qualification of the frozen candidate bytes."""
from pathlib import Path
import hashlib,importlib,json,os,sys
ROOT=Path(__file__).resolve().parents[1];Q=Path(__file__).resolve().parent
sys.path[:0]=[str(ROOT/'controller'),str(ROOT)]
os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD']='1'
import pytest
files=sorted((ROOT/'controller').glob('*.py'))+[ROOT/name for name in ('m1_v11_work.py','publication.py','response_loss.py')]
hashes={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
assert not (Q/'final-run-sources-v2.json').exists()
(Q/'final-run-sources-v2.json').write_text(json.dumps(hashes,indent=2),encoding='utf-8')
origins={}
for name in ('okto_nexus','nexus_connector_core','okto_nexus.adapters.inbound.cli.work',
             'okto_nexus.application.terminal_work','cli_flow','controller','independent_controller'):
    module=importlib.import_module(name);path=Path(module.__file__).resolve()
    origins[name]={'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    if name.startswith(('okto_nexus','nexus_connector')):assert path.is_relative_to(Path(sys.prefix).resolve())
(Q/'module-origins.json').write_text(json.dumps(origins,indent=2),encoding='utf-8')
code=pytest.main(['-q','-p','no:cacheprovider',*[str(p) for p in sorted((ROOT/'controller').glob('test_*.py'))],
                 '--basetemp='+str(Q/'final-tmp'),'--junitxml='+str(Q/'final.xml')])
assert all(hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest for name,digest in hashes.items())
raise SystemExit(code)
