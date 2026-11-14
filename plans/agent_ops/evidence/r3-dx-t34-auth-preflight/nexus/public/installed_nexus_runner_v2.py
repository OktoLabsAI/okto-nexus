"""Run only affected offline fixtures against installed product bytes."""
from pathlib import Path
import hashlib
import json
import os
import sys

root = Path(__file__).resolve().parent
os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD'] = '1'
repo = root / 'installed-fixtures'
sys.path[:0] = [str(repo / 'tests'), str(repo / 'tests/execution_r4')]
import pytest
from okto_nexus.application import connection_test, terminal_connection
import nexus_connector_core
prefix = Path(sys.prefix).resolve() / 'Lib/site-packages'
def origins():
    result = {}
    for name, module in list(sys.modules.items()):
        if name.startswith(('okto_nexus', 'nexus_connector_core')) and getattr(module, '__file__', None):
            path = Path(module.__file__).resolve()
            assert path.is_relative_to(prefix), (name, str(path))
            result[name] = {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    return result
assert sys.flags.isolated and 'PYTHONPATH' not in os.environ
origins()
config = root / 'installed-pytest.ini'
config.write_text('[pytest]\n', encoding='utf-8')
selected = [str(repo / 'tests/execution_r4/test_connection_test.py'),
            str(repo / 'tests/execution_r4/test_terminal_connect.py') + '::test_provider_login_guidance_preserves_failed_request_without_replay']
code = pytest.main(['-c', str(config), '-o', 'pythonpath=', '-q', '-p', 'no:cacheprovider',
                   '--junitxml=' + str(root / 'installed-nexus-final-v2.xml'), *selected])
(root / 'installed-nexus-origins-v2.json').write_text(json.dumps({'python': sys.executable,
    'isolated': True, 'origins': origins(), 'pytest_exit_code': code}, indent=2) + '\n', encoding='utf-8')
raise SystemExit(code)
