from pathlib import Path
import os,sys
ROOT=Path(__file__).resolve().parent
assert sys.flags.isolated and Path(sys.prefix).resolve()==(ROOT/'venv').resolve()
os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD']='1';sys.path.insert(0,str(ROOT))
import okto_nexus,nexus_connector_core
for mod in (okto_nexus,nexus_connector_core):assert Path(mod.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())
import pytest
raise SystemExit(pytest.main([str(ROOT/'test_lifecycle.py'),str(ROOT/'test_connection_routes.py'),'-q',
    '--confcutdir='+str(ROOT),'--junitxml='+str(ROOT/'offline-reviewed.xml')]))
