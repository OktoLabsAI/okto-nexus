from pathlib import Path
import os,sys
HERE=Path(__file__).resolve().parent
REPO=Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD']='1'
sys.path.insert(0,str(REPO/'src'))
import pytest
raise SystemExit(pytest.main(['-q','-o','addopts=','--junitxml='+str(HERE/'final.xml'),
 str(REPO/'tests/test_service_status_missing_discovery.py'),
 str(REPO/'tests/test_service_launch_recovery.py')+'::test_status_and_recovery_survive_missing_saved_interpreter']))
