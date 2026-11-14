from pathlib import Path
import json
import sys

BASE = Path(__file__).resolve().parent
REPO = Path('D:/Projetos/Techridy/okto-nexus-connector')
CORE = Path('D:/Projetos/Techridy/okto-nexus-connector-core/src')
sys.path[:0] = [str(REPO / 'src'), str(CORE)]
import okto_nexus_connector
import nexus_connector_core
import pytest
print(json.dumps({'python': sys.executable, 'connector': okto_nexus_connector.__file__,
                  'core': nexus_connector_core.__file__}), flush=True)
raise SystemExit(pytest.main(['-q', str(REPO / 'tests/unit/test_bounded_service_supervisor.py'),
    str(REPO / 'tests/unit/test_user_service_lifecycle.py'), str(REPO / 'tests/unit/test_service_upgrade.py'),
    '-k', 'not native_preflight_on_worker_thread',
    '--junitxml=' + str(BASE / 'source-regression-initial.xml'), '--basetemp=' + str(BASE / 'pytest-regression-initial')]))
