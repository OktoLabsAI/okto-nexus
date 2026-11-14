"""Focal installed policy/lifecycle fixtures; no real services or child spawn."""
from pathlib import Path
import os
import sys
ROOT=Path(__file__).resolve().parent
assert sys.flags.isolated and Path(sys.prefix).resolve()==(ROOT/'venv').resolve()
os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD']='1'
sys.path.insert(0,str(ROOT/'installed-tests'))
import nexus_connector_core,okto_nexus,okto_nexus_connector
for module in (nexus_connector_core,okto_nexus,okto_nexus_connector):
    assert Path(module.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())
import pytest
raise SystemExit(pytest.main([*[str(ROOT/'installed-tests'/name) for name in (
    'test_user_service_supervision.py','test_user_service_definition.py',
    'test_service_supervisor.py','test_bounded_service_supervisor.py')],
    '-q','-k','not real_venv_redirector_handshake',
    '--confcutdir='+str(ROOT/'installed-tests'),'--junitxml='+str(ROOT/'installed-supervisor-fixture-fixed.xml')]))
