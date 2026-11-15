from pathlib import Path
import hashlib, importlib, json, os, sys, zipfile
HERE=Path(__file__).resolve().parent
case=sys.argv[1]
only_changed='--only-changed' in sys.argv
prefix=HERE/'venv'
assert Path(sys.prefix).resolve()==prefix.resolve()
origins={}
for package in ('nexus_connector_core','okto_nexus_connector','okto_nexus'):
    mod=importlib.import_module(package)
    path=Path(mod.__file__).resolve()
    assert path.is_relative_to(prefix.resolve()),str(path)
    origins[package]=str(path)
payloads=0
for wheel in (HERE/'wheels').glob('*.whl'):
    with zipfile.ZipFile(wheel) as z:
        for item in z.infolist():
            if item.is_dir() or '.dist-info/' in item.filename: continue
            path=prefix/'Lib/site-packages'/item.filename
            assert path.read_bytes()==z.read(item),str(path)
            payloads+=1
(HERE/(case+'-origins.json')).write_text(json.dumps({'prefix':str(prefix),'origins':origins,'wheel_payloads_equal':payloads},indent=2)+'\n')
os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD']='1'
os.chdir(HERE)
root=HERE/(case+'-source')
sys.path[:0]=[str(root/'tests'),str(root/'tests/execution_r4'),str(root)]
if case=='core':
    tests=[str(root/'tests'/p) for p in ('test_claude_powershell_permissions.py','test_claude_mcp_permissions.py','test_r4_decision_bridge.py')]
elif case=='nexus':
    tests=[str(root/'tests/execution_r4'/p) for p in ('test_native_decisions.py','test_native_decision_provenance.py')]
    if only_changed: tests=[str(root/'tests/execution_r4/test_native_decisions.py')+'::test_public_cas_records_exactly_one_application_and_replay']
else:
    f=str(root/'tests/unit/test_r4_execution.py')
    tests=[f+'::test_native_decision_uses_observed_request_and_same_receipt',
       f+'::test_cross_binding_control_cannot_borrow_a_runtime',
       f+'::test_close_fences_native_ingress_before_native_close',str(HERE/'test_connector_powershell.py')]
    if only_changed: tests=[str(HERE/'test_connector_powershell.py')]
import pytest
raise SystemExit(pytest.main(['-q','-p','pytest_asyncio.plugin','-o','asyncio_mode=auto',*tests,'--junitxml='+str(HERE/(case+'-installed.xml'))]))
