"""Disposable pure-test runner; explicitly installed Core, no product source."""
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import sys
import time
from contextlib import redirect_stdout, redirect_stderr

ROOT = Path(__file__).resolve().parent
Q = Path('C:/Users/jpamb/AppData/Local/Temp/r3-cooperative-drain-09ucmgsr/venv').resolve()
run_name = sys.argv[1]
assert run_name in ('initial', 'final')
home = ROOT / ('home-' + run_name)
home.mkdir(exist_ok=True)
safe = {key: os.environ[key] for key in ('SYSTEMROOT', 'WINDIR', 'COMSPEC') if key in os.environ}
safe.update(HOME=str(home), USERPROFILE=str(home), APPDATA=str(home / 'appdata'),
            LOCALAPPDATA=str(home / 'localappdata'), TEMP=str(home), TMP=str(home),
            PYTEST_DISABLE_PLUGIN_AUTOLOAD='1')
os.environ.clear()
os.environ.update(safe)
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
import nexus_connector_core
import pytest

module = Path(nexus_connector_core.__file__).resolve()
assert module.is_relative_to(Q)
inputs = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
          for name in ('token_collector.py', 'test_token_collector.py', 'run_tests.py')}
started = time.monotonic()
with (ROOT / (run_name + '.log')).open('w', encoding='utf-8') as log:
    with redirect_stdout(log), redirect_stderr(log):
        code = pytest.main([str(ROOT / 'test_token_collector.py'), '-q', '--tb=short',
                            '--junitxml=' + str(ROOT / (run_name + '.xml'))])
result = {'exit_code': int(code), 'elapsed_seconds': time.monotonic() - started,
          'core_version': importlib.metadata.version('okto-nexus-connector-core'),
          'core_import': str(module), 'python': sys.version.split()[0],
          'isolated_interpreter': bool(sys.flags.isolated), 'environment_keys': sorted(os.environ),
          'scope': 'pure synthetic translation and deterministic accounting; no native/provider/HTTP',
          'input_hashes_before': inputs,
          'input_hashes_unchanged': inputs == {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                                             for name in inputs}}
(ROOT / (run_name + '-result.json')).write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
print(json.dumps(result))
raise SystemExit(int(code))
