from pathlib import Path
import os,sys
HERE=Path(__file__).resolve().parent
os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD']='1'
import okto_nexus,pytest
assert Path(okto_nexus.__file__).resolve().is_relative_to(HERE/'venv')
raise SystemExit(pytest.main(['-q','-o','pythonpath=','-o','addopts=','--junitxml='+str(HERE/'installed.xml'),
 str(HERE/'nexus-source/tests/test_service_status_missing_discovery.py'),
 str(HERE/'nexus-source/tests/test_service_launch_recovery.py')+'::test_status_and_recovery_survive_missing_saved_interpreter']))
