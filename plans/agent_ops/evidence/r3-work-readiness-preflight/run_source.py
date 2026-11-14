from pathlib import Path
import os,sys
ROOT=Path(__file__).resolve().parent
repo=Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
sys.path[:0]=[str(repo/'src'),str(repo/'tests'),str(repo/'tests/execution_r4')]
os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD']='1'
import pytest
files=['test_work_readiness_preflight.py','test_service_inspection.py','execution_r4/test_terminal_work.py','execution_r4/test_terminal_authorization.py','execution_r4/test_remote_operator_terminal.py']
raise SystemExit(pytest.main([*[str(repo/'tests'/f) for f in files],'-q','--junitxml='+str(ROOT/'source.xml')]))
