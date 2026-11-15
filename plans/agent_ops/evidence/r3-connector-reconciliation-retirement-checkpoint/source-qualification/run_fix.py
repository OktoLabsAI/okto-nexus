from pathlib import Path
import os,sys
HERE=Path(__file__).resolve().parent
ROOT=Path('D:/Projetos/Techridy/okto-nexus-connector')
sys.path[:0]=[str(ROOT/'src'),str(ROOT)]
os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD']='1'
os.chdir(ROOT)
import pytest
tests=['tests/unit/test_reconciliation_checkpoint.py']
if '--new-only' not in sys.argv:
 tests += ['tests/unit/test_session_release_recovery.py','tests/unit/test_session_release_commit_cuts.py']
if '--race-only' in sys.argv:
 tests=['tests/unit/test_reconciliation_checkpoint.py::test_next_report_cannot_lend_its_facts_to_prior_ack',
        'tests/unit/test_session_release_recovery.py::test_reconciled_release_checkpoints_in_background_without_delaying_ready']
raise SystemExit(pytest.main(['-q','-x','--tb=short','-p','pytest_asyncio.plugin',*tests,
 '--junitxml='+str(HERE/'fix-final.xml')]))
