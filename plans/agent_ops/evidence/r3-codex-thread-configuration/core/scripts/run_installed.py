import contextlib
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

out = Path(__file__).parent
# Reuse explicitly located dependencies read-only; -I does not execute their
# .pth files. The qualified Core itself must resolve to this fresh venv.
sys.path.append('C:/Users/jpamb/AppData/Roaming/Python/Python313/site-packages')
import nexus_connector_core
import pytest

origin = Path(nexus_connector_core.__file__).resolve()
assert origin.is_relative_to(out / 'venv/Lib/site-packages')
nodes = ['tests/test_codex_thread_configuration.py', 'tests/test_configuration_events.py',
         'tests/test_codex_resume.py', 'tests/test_native_runtime_bridge.py',
         'tests/test_codex_extracted.py', 'tests/test_codex_handshake.py',
         'tests/test_codex_output_correlation.py', 'tests/test_codex_mcp_elicitation.py',
         'tests/test_codex_0159_qualification.py']
xml = out / 'installed-final.xml'
log = out / 'installed-final.log'
assert not xml.exists() and not log.exists()
with log.open('w', encoding='utf-8') as stream, contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
    code = pytest.main(['-q', '--tb=short', '--junitxml=' + str(xml), *nodes])
doc = ET.parse(xml)
cases = doc.findall('.//testcase')
loaded = {name: str(Path(module.__file__).resolve()) for name, module in sys.modules.items()
          if name.startswith('nexus_connector_core') and getattr(module, '__file__', None)}
assert all(Path(path).is_relative_to(out / 'venv/Lib/site-packages') for path in loaded.values())
result = {'exit_code': int(code), 'python': sys.executable, 'core_origin': str(origin),
          'nodes': nodes, 'tests': len(cases), 'failures': len(doc.findall('.//failure')),
          'errors': len(doc.findall('.//error')), 'skipped': len(doc.findall('.//skipped')),
          'xml_sha256': hashlib.sha256(xml.read_bytes()).hexdigest(), 'imports': loaded,
          'dependency_versions': {name: importlib.metadata.version(name) for name in (
              'okto-nexus-connector-core', 'mcp', 'rfc8785', 'jsonschema', 'anyio', 'pytest')},
          'limits': 'Synthetic transport/owned Python peers only; no provider, native Codex, credentials or personal config.'}
(out / 'installed-final.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
print(json.dumps({key: value for key, value in result.items() if key != 'imports'}))
raise SystemExit(code)
