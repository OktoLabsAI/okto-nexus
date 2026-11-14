from pathlib import Path
import os,sys
ROOT=Path(__file__).resolve().parent
name=sys.argv[1]
repo=Path('D:/Projetos/Techridy/okto_labs_okto_nexus' if name=='nexus' else 'D:/Projetos/Techridy/okto-nexus-connector')
tests=repo/('tests' if name=='nexus' else 'tests/unit')
sys.path[:0]=[str(repo/'src'),str(tests)]
os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD']='1'
import pytest
raise SystemExit(pytest.main([str(tests/'test_service_environment_streaming.py'),
    str(tests/'test_service_upgrade.py')+'::test_installed_payload_change_is_detected_before_bootstrap',
    str(tests/'test_service_upgrade.py')+'::test_environment_probe_timeout_has_stable_actionable_diagnostic',
    '-q','--confcutdir='+str(tests),'--junitxml='+str(ROOT/(name+'-source.xml'))]))
