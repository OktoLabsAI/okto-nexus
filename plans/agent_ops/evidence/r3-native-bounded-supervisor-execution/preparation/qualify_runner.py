"""Pure runner fixtures against isolated installed products; no native campaign."""
from pathlib import Path
import json
import os
import sys

ROOT=Path(__file__).resolve().parent
assert sys.flags.isolated and Path(sys.prefix).resolve()==(ROOT/'venv').resolve()
os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD']='1'
sys.path.insert(0,str(ROOT))
import nexus_connector_core,okto_nexus,okto_nexus_connector
for module in (nexus_connector_core,okto_nexus,okto_nexus_connector):
    assert Path(module.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())
import pytest
raise SystemExit(pytest.main([str(ROOT/'test_runner.py'),'-q','--confcutdir='+str(ROOT),
    '--junitxml='+str(ROOT/'runner-final-reviewed.xml')]))
