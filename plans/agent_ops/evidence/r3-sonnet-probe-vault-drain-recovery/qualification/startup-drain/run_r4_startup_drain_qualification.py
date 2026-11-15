import os
from pathlib import Path
import sys

ROOT = Path('D:/Projetos/Techridy/okto-nexus-connector')
OUT = Path('C:/Users/jpamb/AppData/Local/Temp/r3-r4-startup-drain-qualification')
OUT.mkdir(exist_ok=True)
os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD'] = '1'
sys.path[:0] = [str(ROOT / 'src'), str(ROOT)]
os.chdir(ROOT)
import okto_nexus_connector.daemon.r4_control as observed
assert Path(observed.__file__).resolve() == (ROOT / 'src/okto_nexus_connector/daemon/r4_control.py').resolve()
import pytest
raise SystemExit(pytest.main(['-q', '-p', 'pytest_asyncio.plugin',
    'tests/unit/test_r4_startup_drain.py', 'tests/unit/test_r4_daemon_control.py',
    'tests/unit/test_r4_operator_drain.py',
    '--junitxml=' + str(OUT / 'final.xml')]))
