"""Seal an explicit metadata/report allowlist; never collect credential files."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
QUALIFIED = ROOT / 'qualified'
verified = subprocess.run([sys.executable, str(ROOT / 'verify_release.py'),
    str(QUALIFIED / 'package-proof.json')], capture_output=True, text=True, check=True)
result = json.loads(verified.stdout)
with (QUALIFIED / 'verification-final.json').open('x', encoding='utf-8') as target:
    json.dump(result, target, indent=2)
scripts = ['prepare.py', 'build_release.py', 'qualify_installed.py', 'verify_release.py',
    'server_entry.py', 'start_server.py', 'stop_server.py', 'smoke_http.py',
    'qualification_management.py', 'collect_proof.py', 'preparation.json']
reports = ['package-proof.json', 'installed-qualification.json',
    'pr09-observation-installed-initial.xml', 'real-http-smoke.json', 'server-import-proof.json',
    'server.json', 'server-owner.json', 'qualification-herdr-credential.metadata.json',
    'verification-final.json', 'wheel-build.log', 'venv-create.log', 'wheel-install.log']
paths = [ROOT / name for name in scripts] + [QUALIFIED / name for name in reports]
manifest = {'revision': 1, 'scope': 'PR09 installed wheel qualification and isolated real Nexus HTTP',
    'credential_policy': 'Only an explicit non-secret evidence allowlist; bearer files excluded and never hashed',
    'excluded_private_files': ['qualified/qualification-credential.json',
        'qualified/qualification-herdr-credential.json'], 'artifacts': []}
for path in paths:
    raw = path.read_bytes()
    item = {'path': str(path), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
    if path.suffix == '.xml':
        item['suites'] = [dict(s.attrib) for s in ET.fromstring(raw).iter('testsuite')]
    manifest['artifacts'].append(item)
with (QUALIFIED / 'evidence-manifest.json').open('x', encoding='utf-8') as target:
    json.dump(manifest, target, indent=2)
print(json.dumps({'result': result['result'], 'package_files': result['files'],
    'artifacts': len(manifest['artifacts']), 'manifest': str(QUALIFIED / 'evidence-manifest.json')}))
