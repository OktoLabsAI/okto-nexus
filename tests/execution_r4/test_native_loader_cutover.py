"""Server composition no longer loads duplicate native protocol implementations."""
import subprocess
import sys
from pathlib import Path

from okto_nexus.adapters.inbound.mcp.tools import harness


def test_clean_server_composition_does_not_import_legacy_native_loaders():
    # Resolve the same source/package under test, independent of shell cwd.
    package_root = str(Path(harness.__file__).resolve().parents[5])
    program = 'import sys\nsys.path.insert(0, ' + repr(package_root) + ')\n' + '''
import importlib.util
from okto_nexus.adapters.inbound.http.app import build_app
from okto_nexus.adapters.inbound.mcp.tools.harness import _legacy_capabilities_catalog, _default_connector_factories
from okto_nexus.errors import OktoNexusError
assert len(_legacy_capabilities_catalog()) == 4
for factory in _default_connector_factories().values():
    try:
        factory(project_root='/unused', backend={})
    except OktoNexusError as error:
        assert error.code == 'CONFLICT' and 'canonical runtime binding' in error.message
    else:
        raise AssertionError('Legacy native constructor remains enabled')
for name in ('pi', 'codex', 'claude_code_stream', 'claude_code_attach'):
    assert 'okto_nexus.adapters.outbound.harness.' + name not in sys.modules
    assert importlib.util.find_spec('okto_nexus.adapters.outbound.harness.' + name) is None
assert importlib.util.find_spec('legacy_native_fixture') is None
'''
    result = subprocess.run(['rtk', 'proxy', sys.executable, '-I', '-c', program],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
