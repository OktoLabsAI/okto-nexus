from pathlib import Path
import os,sys
HERE=Path(__file__).resolve().parent
assert Path(sys.prefix).resolve()==(HERE.parent/'package/venv').resolve()
os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD']='1'
import pytest
raise SystemExit(pytest.main([str(HERE/'test_composition.py'),'-q','--rootdir='+str(HERE),'--junitxml='+str(HERE/'composition.xml')]))
