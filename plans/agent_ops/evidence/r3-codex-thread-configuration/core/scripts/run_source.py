"""Focused synthetic qualification; never invokes a provider or native CLI."""
import contextlib
import hashlib
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

root = Path('D:/Projetos/Techridy/okto-nexus-connector-core')
out = Path(__file__).parent
label = sys.argv[1]
nodes = sys.argv[2:]
paths = [
    'src/nexus_connector_core/native/codex_thread_configuration.py',
    'src/nexus_connector_core/native/adapters/codex.py',
    'src/nexus_connector_core/native/runtime_bridge.py',
    'tests/test_codex_thread_configuration.py', 'tests/test_codex_resume.py',
]
before = {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in paths}
sys.path.insert(0, str(root / 'src'))
import nexus_connector_core
import pytest

xml = out / (label + '.xml')
log = out / (label + '.log')
assert not xml.exists() and not log.exists()
with log.open('w', encoding='utf-8') as stream, contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
    code = pytest.main(['-q', '-o', 'console_output_style=progress', '--tb=short',
                        '--junitxml=' + str(xml), *nodes])
after = {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in paths}
doc = ET.parse(xml)
cases = doc.findall('.//testcase')
result = {'label': label, 'exit_code': int(code), 'python': sys.executable,
          'core_import': nexus_connector_core.__file__, 'nodes': nodes,
          'input_hashes': before, 'inputs_unchanged': before == after,
          'tests': len(cases), 'failures': len(doc.findall('.//failure')),
          'errors': len(doc.findall('.//error')), 'skipped': len(doc.findall('.//skipped')),
          'xml': str(xml), 'log': str(log), 'provider_or_native_process': False}
(out / (label + '.json')).write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
print(json.dumps({key: value for key, value in result.items() if key != 'input_hashes'}))
raise SystemExit(code)
