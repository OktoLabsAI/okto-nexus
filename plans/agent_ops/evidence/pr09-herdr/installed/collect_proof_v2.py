"""Seal V2 package validation while preserving all V1 evidence and Server."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
QUALIFIED = ROOT / 'qualified-v2'
verified = subprocess.run([sys.executable, str(ROOT / 'verify_release.py'),
    str(QUALIFIED / 'package-proof.json')], capture_output=True, text=True, check=True)
result = json.loads(verified.stdout)
old = json.loads((ROOT / 'qualified/package-proof.json').read_text())
old_installed = Path(old['installed_package'])
files = {path.relative_to(old_installed).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
    for path in old_installed.rglob('*') if path.is_file() and '__pycache__' not in path.parts
    and not path.name.endswith(('.pyc', '.pyo'))}
assert files == {name: item['installed_sha256'] for name, item in old['files'].items()}, 'Retained V1 installed package changed'
with (QUALIFIED / 'verification-final.json').open('x', encoding='utf-8') as target:
    json.dump(dict(result, retained_v1_installed_package_unchanged=True), target, indent=2)
paths = [ROOT / name for name in ['prepare_v2.py', 'build_release_v2.py',
    'qualify_installed_v2.py', 'verify_release.py', 'collect_proof_v2.py']]
paths += [QUALIFIED / name for name in ['package-proof.json', 'installed-qualification.json',
    'pr09-observation-installed-v2-initial.xml', 'verification-final.json', 'console-observation.json',
    'wheel-build.log', 'venv-create.log', 'wheel-install.log']]
paths += [ROOT / 'qualified' / name for name in ['package-proof.json',
    'real-http-smoke.json', 'server-import-proof.json', 'evidence-manifest.json']]
manifest = {'revision': 2, 'scope': 'V2 installed wheel; retained V1 Server unchanged outside the optional CLI transport',
    'credential_policy': 'Explicit allowlist only; bearer files excluded and never hashed', 'artifacts': []}
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
