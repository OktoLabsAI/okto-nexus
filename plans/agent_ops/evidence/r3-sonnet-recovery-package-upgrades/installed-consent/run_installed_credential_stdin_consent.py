from pathlib import Path
import hashlib
import json
import os
import sys
import tempfile

os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD'] = '1'
root = Path('C:/Users/jpamb/AppData/Local/Temp/sonnet-canonical-recovery-proposal-7oq808_t')
installation = root / 'package/installation.json'
assert hashlib.sha256(installation.read_bytes()).hexdigest() == 'a9f03ee93bfff21c5ea3fa530c4c2259180770027a0674c82fbe0fb774fa221c'
assert Path(sys.prefix).resolve() == (root / 'package/venv').resolve()
from okto_nexus_connector.cli.commands import connect, connect_setup, identity
import pytest

out = Path(tempfile.mkdtemp(prefix='r3-installed-credential-consent-'))
origins = {}
for module in (connect, connect_setup, identity):
    path = Path(module.__file__).resolve()
    assert path.is_relative_to(Path(sys.prefix).resolve())
    origins[module.__name__] = {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
(out / 'module-origins.json').write_text(json.dumps(origins, indent=2)+'\n', encoding='utf-8')
print('EVIDENCE', out, flush=True)
print('INSTALLED_PREFIX', sys.prefix, flush=True)
raise SystemExit(pytest.main([
    '-p', 'pytest_asyncio.plugin', '-q', '-o', 'asyncio_mode=auto', '-o', 'asyncio_default_fixture_loop_scope=function',
    str(Path(__file__).with_name('test_installed_credential_stdin_consent.py')),
    '--junitxml=' + str(out / 'installed.xml'),
    '--basetemp=' + str(out / 'fixtures'),
]))
