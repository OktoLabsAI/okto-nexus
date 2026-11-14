from pathlib import Path
import hashlib,json,os,sys
H=Path(__file__).resolve().parent
W=H.parent
assert Path(sys.prefix).resolve()==(W/'package/venv').resolve()
import okto_nexus.adapters.inbound.cli.work as work
import okto_nexus.adapters.outbound.service_manager.inspection as inspection
pins={}
for name,module in [('work',work),('inspection',inspection)]:
    p=Path(module.__file__);assert p.resolve().is_relative_to(Path(sys.prefix).resolve())
    pins[name]={'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
(H/'installed-origins.json').write_text(json.dumps({'python':sys.executable,'prefix':sys.prefix,'modules':pins,'source_sys_path_injected':False},indent=2),encoding='utf-8')
os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD']='1'
import pytest
raise SystemExit(pytest.main([str(H/'test_installed_preflight.py'),'-q','--rootdir='+str(H),'--junitxml='+str(H/'installed-preflight.xml')]))
