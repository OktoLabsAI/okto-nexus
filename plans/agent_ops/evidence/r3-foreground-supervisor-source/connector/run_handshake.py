from pathlib import Path
import sys
BASE = Path(__file__).resolve().parent
REPO = Path('D:/Projetos/Techridy/okto-nexus-connector')
sys.path[:0] = [str(REPO / 'src'), 'D:/Projetos/Techridy/okto-nexus-connector-core/src']
import pytest
raise SystemExit(pytest.main(['-q', str(REPO / 'tests/unit/test_bounded_service_supervisor.py'),
    '-k', 'real_venv_redirector or false_ancestry', '--junitxml=' + str(BASE / 'handshake-initial.xml'),
    '--basetemp=' + str(BASE / 'pytest-handshake-initial')]))
