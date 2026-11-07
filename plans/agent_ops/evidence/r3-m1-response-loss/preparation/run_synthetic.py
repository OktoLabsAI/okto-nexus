"""Only deterministic instrumentation tests and installed ASGI synthetic flow.

No executable campaign/provider mode is implemented or accepted here.
"""
import hashlib
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parent
EXPECTED = Path(r'C:/Users/jpamb/AppData/Local/Temp/r3-cooperative-drain-09ucmgsr/venv').resolve()
if Path(sys.prefix).resolve() != EXPECTED:
    raise SystemExit('Run only with the pinned installed Q venv python -I.')
if sys.argv[1:] not in ([], ['--crash-check']):
    raise SystemExit('Only no arguments or --crash-check are supported; no campaign mode.')
sys.path[:0] = [str(ROOT), str(ROOT/'fixtures')]
import okto_nexus
import nexus_connector_core
import okto_nexus_connector
modules = (okto_nexus, nexus_connector_core, okto_nexus_connector)
assert all(Path(m.__file__).resolve().is_relative_to(EXPECTED) for m in modules)
proof = {'scope': 'installed ASGI/SQLite/Core with synthetic native peer only',
         'modules': {m.__name__: {'path': m.__file__, 'sha256': hashlib.sha256(Path(m.__file__).read_bytes()).hexdigest()}
                     for m in modules},
         'native_provider': False, 'vault': False, 'os_service': False,
         'connector_topology_exercised': False}
RUN = Path(tempfile.mkdtemp(prefix='synthetic-run-', dir=ROOT))
(RUN/'installed-import-proof.json').write_text(json.dumps(proof, indent=2)+'\n', encoding='utf-8')
print(json.dumps({'synthetic_run': str(RUN)}), flush=True)
inputs = [p for m in modules for p in Path(m.__file__).parent.rglob('*')
          if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc']
inputs += list((ROOT/'fixtures').glob('*.py'))
inputs += [ROOT/n for n in ('response_loss.py', 'test_response_loss.py', 'test_installed_flow.py',
                           'run_synthetic.py', 'pytest.ini', 'fixture-manifest.json')]
def hashes():
    return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
before = hashes()
(RUN/'input-hashes-before.json').write_text(json.dumps(before, indent=2)+'\n', encoding='utf-8')
for item in json.loads((ROOT/'fixture-manifest.json').read_text()):
    assert before[str(ROOT/'fixtures'/item['name'])] == item['sha256']
import pytest
tests = [str(ROOT/'test_response_loss.py'), str(ROOT/'test_installed_flow.py')]
if sys.argv[1:] == ['--crash-check']:
    tests = [str(ROOT/'test_response_loss.py') + '::test_crash_after_reservation_blocks_new_work_but_not_inspection_or_close']
status = pytest.main(['-q', '-c', str(ROOT/'pytest.ini'), '--confcutdir', str(ROOT),
    *tests,
    '--junitxml', str(RUN/'synthetic-results.xml'), '--basetemp', str(RUN/'test-state')])
after = hashes()
(RUN/'input-hashes-after.json').write_text(json.dumps(after, indent=2)+'\n', encoding='utf-8')
shadowed = [name for name, module in tuple(sys.modules.items())
            if name.split('.')[0] in {'okto_nexus', 'nexus_connector_core', 'okto_nexus_connector'}
            and getattr(module, '__file__', None)
            and not Path(module.__file__).resolve().is_relative_to(EXPECTED)]
summary = {'pytest_exit': int(status), 'input_files': len(before), 'inputs_unchanged': before == after,
           'shadowed_product_modules': shadowed, 'scope': proof['scope'],
           'native_provider': False, 'os_service': False, 'vault': False,
           'connector_topology_exercised': False}
(RUN/'status.json').write_text(json.dumps(summary, indent=2)+'\n', encoding='utf-8')
assert before == after and not shadowed
raise SystemExit(status)
