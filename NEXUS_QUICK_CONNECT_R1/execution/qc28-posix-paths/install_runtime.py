"""Continue after uv-version whitespace oracle; verified own binary only."""
import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('qc28_bootstrap', HERE / 'bootstrap.py')
boot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(boot)
root = boot.ROOT
download = json.loads((root / 'uv-download.json').read_text())
assert hashlib.sha256((root / 'uv').read_bytes()).hexdigest() == download['uv_binary_sha256']
assert (root / 'uv-version.log').read_text().split() == ['uv', '0.10.7']
boot.run('python-install', [str(root / 'uv'), 'python', 'install', '3.13.1', '--install-dir', str(root / 'python'),
    '--no-bin', '--no-registry', '--no-config', '--cache-dir', str(root / 'cache')])
boot.write('bootstrap-ready.json', dict(status='TEMP_RUNTIME_READY', root=str(root),
    antecedent='Version output uv 0.10.7 has no trailing build annotation; original whitespace oracle failed before Python install.'))
