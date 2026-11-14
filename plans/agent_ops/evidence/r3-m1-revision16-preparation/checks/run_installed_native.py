from pathlib import Path
import hashlib,json,os,sys
H=Path(__file__).resolve().parent;W=H.parent
assert Path(sys.prefix).resolve()==(W/'package/venv').resolve()
import okto_nexus.application.execution_native_decisions as decisions
import okto_nexus.application.attention_authority as attention
import nexus_connector_core as core
origins={}
for name,m in [('decisions',decisions),('attention',attention),('core',core)]:
    p=Path(m.__file__);assert p.resolve().is_relative_to(Path(sys.prefix).resolve())
    origins[name]={'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
(H/'installed-native-origins.json').write_text(json.dumps({'python':sys.executable,'prefix':sys.prefix,'modules':origins,'repository_source_imports':False},indent=2)+'\n',encoding='utf-8')
sys.path[:0]=[str(H/'tests'),str(H/'tests/execution_r4')]
os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD']='1'
import pytest
raise SystemExit(pytest.main([*[str(H/'tests/execution_r4'/name) for name in ['test_native_decision_provenance.py','test_native_decisions.py','test_managed_native_decisions.py']],
 '-q','--rootdir='+str(H),'--junitxml='+str(H/'installed-native.xml')]))
