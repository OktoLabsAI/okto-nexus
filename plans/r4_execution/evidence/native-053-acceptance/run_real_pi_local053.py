from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys

root = Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
out = Path('C:/Users/jpamb/AppData/Local/Temp/nexus-real-local-only-053-pi')
out.mkdir(exist_ok=True)
source = root/'tests/execution_r4/test_real_embedded_pi.py'
text = source.read_text(encoding='utf-8')
old = "    monkeypatch.setattr(runtime_v1,'protocol_info',lambda:{**info,'remote_execution_ready':True})\n    monkeypatch.setattr(embedded_dispatch,'protocol_info',lambda:{**info,'remote_execution_ready':True})"
assert old in text
text = text.replace(old, "    assert info['remote_execution_ready'] is True\n    assert embedded_dispatch.protocol_info() == info")
text = text.replace("'server_release_gate_override':True", "'server_release_gate_override':False")
test = out/source.name
test.write_text(text, encoding='utf-8')
(out/'pytest.ini').write_text('[pytest]\n')
env = os.environ.copy()
env['OKTO_NEXUS_REAL_PI'] = '1'
env['OKTO_NEXUS_REAL_PI_REPORT'] = str(out/'provider.json')
child = "import sys, importlib.util; assert importlib.util.find_spec('okto_nexus_connector') is None; sys.path.insert(0, sys.argv[1]); import pytest; raise SystemExit(pytest.main(sys.argv[2:]))"
command = [sys.executable, '-I', '-X', 'utf8', '-c', child, str(root/'tests/execution_r4'),
           '-c', str(out/'pytest.ini'), str(test), '-q', '--tb=short', '--junitxml='+str(out/'tests.xml')]
report = dict(scope='Real Pi local embedded native tools without Connector; single Windows host',
              python=sys.executable, source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
              candidate_sha256=hashlib.sha256(test.read_bytes()).hexdigest(),
              connector_absence_asserted=True, readiness_override=False, status='RUNNING')
(out/'campaign.json').write_text(json.dumps(report,indent=2)+'\n')
with (out/'pytest.log').open('w',encoding='utf-8') as log:
    result = subprocess.run(command, cwd=out, env=env, stdout=log, stderr=subprocess.STDOUT)
report.update(status='PASS' if result.returncode == 0 else 'FAIL', exit_code=result.returncode)
(out/'campaign.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
raise SystemExit(result.returncode)
