import sys
from pathlib import Path
import tempfile

REPO = Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
OUT = Path(tempfile.mkdtemp(prefix='svc15-stop-observation-'))
sys.path[:0] = [str(REPO / 'src'), 'D:/Projetos/Techridy/okto-nexus-connector-core/src', str(REPO / 'tests')]
import pytest
print(str(OUT), flush=True)
raise SystemExit(pytest.main(['-q', str(REPO / 'tests/test_user_service_installation.py'),
    str(REPO / 'tests/test_service_drain_decision.py'), '-k',
    'stop_persists or stale_stop or stop_positive_identity or stop_transport_loss or stop_same_identity or stop_force_without or local_force_preserves or normal_stop_keeps_old_wire',
    '--junitxml=' + str(OUT / 'source.xml'), '--basetemp=' + str(OUT / 'pytest')]))
