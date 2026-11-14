from pathlib import Path
import sys

BASE = Path(__file__).resolve().parent
REPO = Path('D:/Projetos/Techridy/okto-nexus-connector')
sys.path[:0] = [str(REPO / 'src'), 'D:/Projetos/Techridy/okto-nexus-connector-core/src']
import pytest

raise SystemExit(pytest.main(['-q', str(REPO / 'tests/unit/test_bounded_service_supervisor.py'),
    '-k', 'stop_backoff_scope or restart_after_supervisor_only or terminal_receipt_does_not_report_stopped or lost_parent_with_unknown_child',
    '--junitxml=' + str(BASE / 'source-outcome-delta.xml'), '--basetemp=' + str(BASE / 'pytest-outcome-delta')]))
