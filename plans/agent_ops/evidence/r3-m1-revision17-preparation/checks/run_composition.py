from pathlib import Path
import os,sys
os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD']='1'
H=Path(__file__).resolve().parent
import pytest
raise SystemExit(pytest.main(['-q','-p','no:cacheprovider',str(H/'test_composition.py'),'--junitxml='+str(H/'composition.xml')]))
