from pathlib import Path
import os
import sys

HERE=Path(__file__).resolve().parent
ROOT=Path('D:/Projetos/Techridy/okto-nexus-connector-core')
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests')]
os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD']='1'
os.chdir(ROOT)
import nexus_connector_core.native.native_inputs as module
assert Path(module.__file__).resolve()==(ROOT/'src/nexus_connector_core/native/native_inputs.py').resolve()
import pytest
raise SystemExit(pytest.main(['-q','-p','pytest_asyncio.plugin',
    'tests/test_claude_powershell_permissions.py','tests/test_claude_mcp_permissions.py',
    'tests/test_r4_decision_bridge.py','--junitxml='+str(HERE/'final.xml')]))
