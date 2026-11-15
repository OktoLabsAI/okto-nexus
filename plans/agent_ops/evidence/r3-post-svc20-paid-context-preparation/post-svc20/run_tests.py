from pathlib import Path
import os,sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE));os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD']='1'
import pytest
raise SystemExit(pytest.main([str(HERE/'test_post_svc20.py'),'-q','-p','no:cacheprovider','--junitxml='+str(HERE/'qualification.xml')]))
