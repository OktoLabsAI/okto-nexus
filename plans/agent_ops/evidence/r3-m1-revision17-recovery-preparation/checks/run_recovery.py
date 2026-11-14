from pathlib import Path
import os
os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD']='1'
import pytest
H=Path(__file__).resolve().parent
raise SystemExit(pytest.main(['-q','-p','no:cacheprovider',str(H/'test_recovery.py'),'--junitxml='+str(H/'recovery.xml')]))
