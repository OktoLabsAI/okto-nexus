"""Benign signature recheck after fixing the Job-name argument."""
from pathlib import Path
import importlib.util
import json
import tempfile
import time
import traceback

BASE = Path(__file__).parent
SOURCE = BASE / 'dx04_probe.py'
spec = importlib.util.spec_from_file_location('dx04_benign_signature', SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
root = Path(tempfile.mkdtemp(prefix='dx04-console-signature-v2-'))
config = root / 'worker-config.json'
module.write_json(config, {'root': str(root), 'argv': ['--help']})
result = {'scope': 'Installed Nexus CLI --help only', 'server_started': False,
          'vault_accessed': False, 'native_cli_started': False}
owned = None
try:
    owned = module.OwnedConsole(config, module.environment(root), root)
    deadline = time.monotonic() + 10
    while owned.active() and time.monotonic() < deadline:
        time.sleep(.1)
    result['cleanup'] = owned.contain_and_join(root)
except BaseException:
    result['traceback'] = traceback.format_exc()
finally:
    if owned is not None:
        result['handle_close_errors'] = owned.close_handles()
    for name in ('tty-owner', 'tty-child', 'worker-result', 'watcher-error'):
        value = module.read_json(root / (name + '.json'))
        if value is not None:
            result[name] = value
    (root / 'result.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'directory': str(root), **result}))
