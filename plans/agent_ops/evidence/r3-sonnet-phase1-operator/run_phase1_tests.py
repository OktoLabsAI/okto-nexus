from pathlib import Path
import os
import sys
os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD']='1'
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import pytest
raise SystemExit(pytest.main(['-q','-p','no:cacheprovider',str(HERE/'test_phase1.py'),
    '--junitxml='+str(HERE/'phase1-tests.xml')]))
