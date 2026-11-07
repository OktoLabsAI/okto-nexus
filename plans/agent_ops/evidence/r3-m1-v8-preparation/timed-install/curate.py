"""Retain only prepared scripts, hashes and read-only/synthetic evidence."""
import hashlib
import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET

root = Path(__file__).parent
public = root / 'public'
assert not public.exists()
assert not any((root / name).exists() for name in (
    'installation-reserved.json', 'installation-result.json', 'installation-unknown.json',
    'product-install.stdout.txt', 'product-install.stderr.txt'))
report = json.loads((root / 'dependency-preparation.json').read_text(encoding='utf-8'))
assert report['status'] == 'DEPENDENCIES_ONLY_READY'
assert all(value is None for value in report['probe']['products_find_spec'].values())
xml = ET.parse(root / 'gates-initial.xml')
assert len(xml.findall('.//testcase')) == 27 and not xml.findall('.//failure') and not xml.findall('.//error')
allowlist = [
    'README.md', 'timed_install.py', 'prepare_dependencies.py', 'finalize_preparation.py',
    'test_timed_install.py', 'curate.py', 'base06-contract.json',
    'products-requirements.txt', 'environment.json', 'dependency-manifest.json',
    'dependency-preparation.json', 'dependency-probe.stdout.txt', 'dependency-probe.stderr.txt',
    'direct-interpreter-probe.json', 'direct-interpreter-final.json',
    'direct-interpreter-final.stdout.txt', 'direct-interpreter-final.stderr.txt', 'gates-initial.xml',
    'tested-before-lint/timed_install.py', 'tested-before-lint/finalize_preparation.py',
    'tested-before-lint/test_timed_install.py', 'tested-before-lint/note.json',
]
public.mkdir()
manifest = {}
for name in allowlist:
    source = root / name
    target = public / name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    raw = target.read_bytes()
    manifest[name] = {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw),
                      'source': str(source), 'byte_exact': True}
summary = {'status': 'PREPARED_NOT_EXECUTED_NOT_AUTHORIZED', 'tests': 27,
           'dependency_files': 3209, 'products_installed': False,
           'product_reservation_exists': False, 'provider_services_credentials_used': False,
           'source_environment_modified': False, 'authorization_receipt_created': False,
           'future_payloads_expected': 982,
           'limits': 'No future product installation or BASE-06/M1 acceptance inferred from preparation.'}
(public / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
raw = (public / 'summary.json').read_bytes()
manifest['summary.json'] = {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw), 'generated': True}
(public / 'artifact-manifest.json').write_text(json.dumps({'format': 'okto.evidence.allowlist',
    'version': 1, 'artifacts': manifest}, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'public': str(public), 'artifacts': len(manifest),
                  'manifest_sha256': hashlib.sha256((public / 'artifact-manifest.json').read_bytes()).hexdigest()}))
