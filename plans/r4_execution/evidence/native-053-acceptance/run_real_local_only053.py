from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys

root = Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
adapter = sys.argv[1] if len(sys.argv) > 1 else 'codex_app_server'
out = Path('C:/Users/jpamb/AppData/Local/Temp/nexus-real-local-only-053-py313' + ('-' + adapter if adapter != 'codex_app_server' else ''))
out.mkdir(exist_ok=True)
source = root / 'tests/execution_r4/test_real_embedded_mcp.py'
text = source.read_text(encoding='utf-8')
text = text.replace('codex=Path.home()/"AppData/Roaming/npm/node_modules/@openai/codex/node_modules/@openai/codex-win32-x64/vendor/x86_64-pc-windows-msvc/bin/codex.exe"', 'codex=Path("C:/Users/jpamb/AppData/Local/Temp/okto-codex-01590/node_modules/@openai/codex-win32-x64/vendor/x86_64-pc-windows-msvc/bin/codex.exe")')
old = "    monkeypatch.setattr(runtime_v1,'protocol_info',lambda:{**info,'remote_execution_ready':True})\n    monkeypatch.setattr(embedded_dispatch,'protocol_info',lambda:{**info,'remote_execution_ready':True})"
assert old in text
text = text.replace(old, "    assert info['remote_execution_ready'] is True\n    assert embedded_dispatch.protocol_info() == info")
text = text.replace("'server_release_gate_override':True", "'server_release_gate_override':False")
test = out / source.name
test.write_text(text, encoding='utf-8')
(out/'pytest.ini').write_text('[pytest]\n', encoding='utf-8')
env = os.environ.copy()
env['OKTO_NEXUS_REAL_MCP'] = '1'
env['OKTO_NEXUS_REAL_MCP_REPORT'] = str(out/'provider')
child = """
import sys
sys.path.insert(0, sys.argv[1])
import importlib.util
assert importlib.util.find_spec('okto_nexus_connector') is None
import pytest
raise SystemExit(pytest.main(sys.argv[2:]))
"""
command = [sys.executable, '-I', '-X', 'utf8', '-c', child,
           str(root/'tests/execution_r4'), '-c', str(out/'pytest.ini'),
           str(test)+'::test_real_provider_uses_automatic_local_dispatch_and_http_work['+adapter+']',
           '-q', '--tb=short', '--junitxml='+str(out/'tests.xml')]
report = {'scope':'Real Windows Codex embedded loopback; not independent-machine acceptance',
          'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
          'candidate_sha256':hashlib.sha256(test.read_bytes()).hexdigest(),
          'python':sys.executable,'readiness_override':False,'connector_absence_asserted':True,'status':'RUNNING'}
(out/'campaign.json').write_text(json.dumps(report, indent=2)+'\n')
with (out/'pytest.log').open('w', encoding='utf-8') as log:
    result = subprocess.run(command, cwd=out, env=env, stdout=log, stderr=subprocess.STDOUT)
report['exit_code'] = result.returncode
report['status'] = 'PASS' if result.returncode == 0 else 'FAIL'
(out/'campaign.json').write_text(json.dumps(report, indent=2)+'\n')
print(json.dumps(report, indent=2))
raise SystemExit(result.returncode)
