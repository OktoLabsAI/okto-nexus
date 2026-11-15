import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD']='1'
import pytest
raise SystemExit(pytest.main(['-q',str(HERE/'test_redacted_assistant.py'),
                             '--junitxml='+str(HERE/'final.xml')]))
