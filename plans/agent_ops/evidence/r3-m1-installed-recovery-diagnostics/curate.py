"""Finite public allowlist; never copy test profiles, databases or private state."""
from pathlib import Path
import hashlib
import json
import shutil
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT / 'public'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(name):
    return json.loads((ROOT / name).read_text(encoding='utf-8'))


def write(name, data):
    (PUBLIC / name).write_bytes((json.dumps(data, indent=2) + '\n').encode('utf-8'))


campaign = read('canonical/campaign.json')
assert campaign['status'] == 'PASS' and campaign['exit_code'] == 0 and campaign['changed_inputs'] == []
cases = list(ET.parse(ROOT / 'canonical/tests.xml').iter('testcase'))
assert len(cases) == 59
assert len({(case.attrib['classname'], case.attrib['name']) for case in cases}) == len(cases)
assert not any(e.tag in ('error', 'failure', 'skipped') for case in cases for e in case)
counts = {}
for case in cases:
    name = case.attrib['classname']
    counts[name] = counts.get(name, 0) + 1
before = read('package-proof-before.json')
after = read('package-proof-after.json')
assert before == after
assert read('pip-check-result.json')['exit_code'] == 0
assert read('pip-check-after-result.json')['exit_code'] == 0
PUBLIC.mkdir(exist_ok=False)
allowlist = [
    'prepare_dependencies.py', 'qualify.py', 'curate.py',
    'dependency-preparation.json', 'dependency-manifest.json',
    'dependency-probe.stdout.txt', 'dependency-probe.stderr.txt',
    'snapshot-inputs.json', 'wheel-result.json', 'requirements-products.txt',
    'git-archive-result.json', 'build-result.json', 'build.stdout.txt', 'build.stderr.txt',
    'install-result.json', 'install.stdout.txt', 'install.stderr.txt',
    'pip-check-result.json', 'pip-check.stdout.txt', 'pip-check.stderr.txt',
    'pip-check-after-result.json', 'pip-check-after.stdout.txt', 'pip-check-after.stderr.txt',
    'import-proof-result.json', 'import-proof.stdout.txt', 'import-proof.stderr.txt',
    'package-proof-before.json', 'package-proof-after.json',
    'installed-tests-process.json', 'installed-tests-result.json',
    'installed-tests.stdout.txt', 'installed-tests.stderr.txt',
    'canonical/installed.json', 'canonical/campaign.json', 'canonical/tests.xml',
]
for name in allowlist:
    target = PUBLIC / name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / name, target)
wheel = read('wheel-result.json')
source_files = [
    'src/okto_nexus/adapters/outbound/sqlite/diagnostics.py',
    'src/okto_nexus/adapters/outbound/sqlite/write_gate.py',
    'src/okto_nexus/bootstrap/embedded_agent_recovery.py',
    *campaign['tests'], 'tools/ci_installed.py',
]
source_hashes = {}
for name in source_files:
    path = ROOT / 'source' / name
    source_hashes[name] = sha(path)
    target = PUBLIC / 'source' / name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(path, target)
qualification = {
    'status': 'INSTALLED_RECOVERY_DIAGNOSTICS_VERIFIED',
    'source_commit': wheel['commit'], 'wheel': wheel['wheel'], 'wheel_sha256': wheel['sha256'],
    'installed_unique_cases': 59, 'counts_by_module': counts,
    'errors': 0, 'failures': 0, 'skipped': 0,
    'canonical_ci_installed_harness': True, 'ci_input_count': len(campaign['input_hashes']),
    'ci_inputs_unchanged': True, 'snapshot_inputs_unchanged': True,
    'snapshot_file_count': after['snapshot_input_count'],
    'package_payloads': {module: {'files': value['payload_count'], 'sha256': value['sha256'],
                                'before_after_match': True}
                         for module, value in after['products'].items()},
    'package_payload_total': after['total_payloads'], 'pip_check_before_after': 'PASS',
    'interpreter': {'path': str(ROOT / 'venv/Scripts/python.exe'),
                    'sha256': sha(ROOT / 'venv/Scripts/python.exe'),
                    'payload_count_excludes_python': True},
    'source_files': source_hashes, 'offline_no_index_no_deps_require_hashes': True,
    'requirements_encoding': 'UTF-8 LF', 'previous_prefixes_modified': False,
    'native_provider_calls': 0, 'native_service_actions': 0,
    'limits': [
        'Synthetic installed SQLite/recovery/terminal-connect qualification; no M1 or real provider acceptance.',
        'New diagnostics do not identify the unretained historical M1 v9 SQLite cause.',
        'No retry, timeout, locking, containment or effect semantics were changed.',
        'Snapshot is the committed archive, including its canonical Git bytes; no checkout imports are used.',
        'Import-boundary source-only tests were already passed separately and are not counted here.',
    ],
}
write('qualification.json', qualification)
files = {p.relative_to(PUBLIC).as_posix(): {'sha256': sha(p), 'bytes': p.stat().st_size}
         for p in sorted(PUBLIC.rglob('*')) if p.is_file()}
write('artifact-manifest.json', {'version': 1, 'files': files,
    'excluded': ['venv', 'isolated', 'temporary test homes and databases', 'source-snapshot.zip', 'wheel binary']})
print(json.dumps({'public': str(PUBLIC), 'payloads': len(files),
    'manifest_sha256': sha(PUBLIC / 'artifact-manifest.json'),
    'qualification_sha256': sha(PUBLIC / 'qualification.json'),
    'wheel_sha256': wheel['sha256'], 'installed_unique_cases': len(cases)}, indent=2))
