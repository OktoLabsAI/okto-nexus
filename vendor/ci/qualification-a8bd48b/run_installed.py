from pathlib import Path
import importlib,json,os,sys,zipfile
HERE=Path(__file__).resolve().parent
BASE=Path('C:/Users/jpamb/AppData/Local/Temp/r3-core-consumer-integration-h_elhexb')
prefix=HERE/'venv'; assert Path(sys.prefix).resolve()==prefix.resolve()
origins={}
for name in ('nexus_connector_core','okto_nexus_connector','okto_nexus'):
 path=Path(importlib.import_module(name).__file__).resolve()
 assert path.is_relative_to(prefix.resolve()),str(path)
 origins[name]=str(path)
wheels=[next((HERE/'wheels').glob('*.whl')),BASE/'wheels/okto_nexus_connector_core-0.0.14-py3-none-any.whl',BASE/'wheels/okto_nexus-0.3.3-py3-none-any.whl']
payloads=0
for wheel in wheels:
 with zipfile.ZipFile(wheel) as archive:
  for item in archive.infolist():
   if item.is_dir() or '.dist-info/' in item.filename: continue
   assert (prefix/'Lib/site-packages'/item.filename).read_bytes()==archive.read(item),item.filename
   payloads+=1
(HERE/'origins.json').write_text(json.dumps({'origins':origins,'payloads_equal':payloads},indent=2)+'\n')
root=HERE/'connector-source'
sys.path.insert(0,str(root))
os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD']='1'
os.chdir(root)
import pytest
raise SystemExit(pytest.main(['-q','-x','--tb=short','-p','pytest_asyncio.plugin',
 'tests/unit/test_reconciliation_checkpoint.py',
 'tests/unit/test_session_release_recovery.py::test_reconciled_release_checkpoints_in_background_without_delaying_ready',
 'tests/unit/test_session_release_recovery.py::test_recovery_keeps_original_bytes_and_separate_authenticated_proof',
 '--junitxml='+str(HERE/'installed.xml')]))
