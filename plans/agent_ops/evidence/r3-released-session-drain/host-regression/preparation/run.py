from pathlib import Path
import hashlib,json,sys,tempfile,zipfile
root=Path(__file__).parent
assert sys.flags.isolated and len(sys.argv)==2 and sys.argv[1] in ('baseline','corrected')
label=sys.argv[1]
sys.path.insert(0,str(root))
import okto_nexus,nexus_connector_core,okto_nexus_connector
modules=(okto_nexus,nexus_connector_core,okto_nexus_connector)
assert all(Path(m.__file__).resolve().is_relative_to(Path(sys.prefix).resolve()) for m in modules)
if label=='baseline':
    assert Path(sys.prefix).resolve()==Path('C:/Users/jpamb/AppData/Local/Temp/r3-cooperative-drain-09ucmgsr/venv').resolve()
    wheel=Path('C:/Users/jpamb/AppData/Local/Temp/r3-campaign-refresh-0ssbo8pb/native/wheels/okto_nexus_connector_core-0.0.14-py3-none-any.whl')
    assert hashlib.sha256(wheel.read_bytes()).hexdigest()=='1407014ea12f7e6f04ac70b9da8dbf8ebd9a57d8021bb5e74437bc22bd274f7a'
    package=Path(nexus_connector_core.__file__).parent
    with zipfile.ZipFile(wheel) as z:
        expected={n.split('/',1)[1]:hashlib.sha256(z.read(n)).hexdigest() for n in z.namelist() if n.startswith('nexus_connector_core/') and not n.endswith('/')}
    actual={p.relative_to(package).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in package.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc'}
    assert actual==expected
run=Path(tempfile.mkdtemp(prefix=label+'-',dir=root))
print(json.dumps({'run':str(run),'label':label}),flush=True)
inputs=list(root.glob('*.py'))+[root/'pytest.ini']
inputs += [p for m in modules for p in Path(m.__file__).parent.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc']
def hashes():return {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
before=hashes();(run/'input-hashes-before.json').write_text(json.dumps(before,indent=2))
import pytest
code=pytest.main(['-q','-c',str(root/'pytest.ini'),'--confcutdir',str(root),
    str(root/'test_service_cooperative_drain.py')+'::test_normally_closed_evicted_session_drains_with_acked_history_and_retained_claim',
    '--basetemp',str(run/'test-state'),'--junitxml',str(run/'results.xml')])
after=hashes();(run/'input-hashes-after.json').write_text(json.dumps(after,indent=2))
shadowed=[name for name,m in tuple(sys.modules.items()) if name.split('.')[0] in {x.__name__ for x in modules}
          and getattr(m,'__file__',None) and not Path(m.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())]
(run/'status.json').write_text(json.dumps({'pytest_exit':int(code),'label':label,'input_files':len(before),
    'inputs_unchanged':before==after,'product_shadow_modules':shadowed,'prefix':sys.prefix,
    'provider':False,'os_services':False,'credential_store':False,'real_m1_mutations':False},indent=2))
assert before==after and not shadowed
raise SystemExit(code)
