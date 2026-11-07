"""Explicit public allowlist; no environments, databases, wheels or personal files."""
import hashlib
import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET

out = Path(__file__).parent
root = Path('D:/Projetos/Techridy/okto-nexus-connector-core')
public = out / 'public'
assert not public.exists()
installed = json.loads((out / 'installed-final.json').read_text(encoding='utf-8'))
assert installed['exit_code'] == 0
assert installed['tests'] == 126 and installed['failures'] == installed['errors'] == installed['skipped'] == 0
hashes = json.loads((out / 'final-source-hashes.json').read_text(encoding='utf-8'))
sha = lambda b: hashlib.sha256(b).hexdigest()
assert all(sha((root / name).read_bytes()) == digest for name, digest in hashes.items())
proof = json.loads((out / 'package-proof.json').read_text(encoding='utf-8'))
for name, digest in proof['files'].items():
    assert sha((root / 'src' / name).read_bytes()) == digest
    assert sha((out / 'venv/Lib/site-packages' / name).read_bytes()) == digest

public.mkdir()
manifest = {}


def retain(source, name):
    target = public / name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    manifest[name] = {'sha256': sha(target.read_bytes()), 'bytes': target.stat().st_size,
                      'source': str(source), 'byte_exact': True}


for label in ('source-initial', 'source-correction', 'source-regression', 'installed-final'):
    for suffix in ('.json', '.xml', '.log'):
        retain(out / (label + suffix), 'reports/' + label + suffix)
for name in ('package-proof.json', 'final-source-hashes.json', 'ruff.json',
             'build.json', 'build.log', 'venv.json', 'venv.log', 'install.json',
             'install.log', 'installed-run.json', 'installed-run.log'):
    retain(out / name, 'qualification/' + name)
for name in ('run_source.py', 'run_installed.py', 'qualify_installed.py', 'curate.py'):
    retain(out / name, 'scripts/' + name)
for name in hashes:
    retain(root / name, 'final-source/' + name)
retain(Path('C:/Users/jpamb/AppData/Local/Temp/core-dx43-readonly-q20ilu5n/review.json'),
       'review/independent-review.json')

identities = {}
attempts = []
for label in ('source-initial', 'source-correction', 'source-regression'):
    xml = ET.parse(out / (label + '.xml'))
    rows = xml.findall('.//testcase')
    attempts.append({'label': label, 'tests': len(rows), 'failures': len(xml.findall('.//failure')),
                     'errors': len(xml.findall('.//error')), 'skipped': len(xml.findall('.//skipped'))})
    for row in rows:
        identity = row.attrib.get('classname', '') + '::' + row.attrib['name']
        identities[identity] = 'PASS' if row.find('failure') is None and row.find('error') is None else 'FAIL'
assert len(identities) == 126 and set(identities.values()) == {'PASS'}
summary = {
    'status': 'QUALIFIED_SYNTHETIC_INSTALLED', 'component': 'okto-nexus-connector-core',
    'version': '0.0.14', 'wheel_sha256': proof['wheel_sha256'],
    'payloads_equal': proof['payload_count'], 'source_unique_passed': len(identities),
    'new_test_identities': 40, 'regression_identities': 86,
    'installed': {key: installed[key] for key in ('tests', 'failures', 'errors', 'skipped', 'core_origin', 'dependency_versions')},
    'attempts': attempts,
    'initial_failure_cause': 'Three synthetic transport fixtures bypassed handshake without setting _compatibility_report. Fixed only the fixture; initial XML/log/hashes retained.',
    'product_change_after_first_run': 'Reordered the text length check before strip to bound work on oversized values; no policy or native command change.',
    'lint': 'Zero new diagnostics. Five existing runtime_bridge diagnostics match HEAD; all other touched Python files pass.',
    'event': {'category': 'lifecycle', 'native_type': 'core/codex_thread_configuration',
              'schema_version': 1, 'sources': ['thread/start/response', 'thread/resume/response'],
              'statuses': ['reported', 'missing', 'invalid'],
              'invalid_reasons': ['invalid_value', 'limit_exceeded', 'unknown_policy_field', 'redacted'],
              'max_payload_bytes': 48000},
    'limits': [
        'Snapshot of reported thread-response metadata at start/resume, not enforcement, live policy, authority, or a provider qualification.',
        'No native CLI/provider, personal configuration, credentials, account, service or paid turn used. Regression peers are owned synthetic Python subprocesses.',
        'No consumer code, pins, ledger, versions, commits or pushes changed by this agent.',
        'Only paths/references are projected; instruction contents, full thread transcripts and unknown top-level response fields are excluded.',
        'Package qualification used an isolated non-editable venv and explicit read-only dependency path; no historical environment was mutated.',
    ],
    'redactions': [], 'artifact_policy': 'Explicit allowlist, exact bytes. No credential-bearing artifact created; retained synthetic markers are intentional test data.',
}
(public / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
manifest['summary.json'] = {'sha256': sha((public / 'summary.json').read_bytes()),
                           'bytes': (public / 'summary.json').stat().st_size, 'generated': True}
(public / 'artifact-manifest.json').write_text(json.dumps({'schema': 1, 'artifacts': manifest}, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'public': str(public), 'artifacts': len(manifest),
                  'manifest_sha256': sha((public / 'artifact-manifest.json').read_bytes()),
                  'source_unique': len(identities), 'installed': installed['tests']}))
