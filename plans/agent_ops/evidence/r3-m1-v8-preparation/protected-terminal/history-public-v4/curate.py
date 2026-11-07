import difflib
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).parent
PREVIOUS = ROOT.parent / 'revision-3/public'
PUBLIC = ROOT / 'public'
PUBLIC.mkdir()
sha = lambda payload: hashlib.sha256(payload).hexdigest()
old_manifest_bytes = (PREVIOUS / 'artifact-manifest.json').read_bytes()
assert sha(old_manifest_bytes) == '1382e08b051e0d004c1012e4548c4d943395ab599bfaf4384239a33265ef8f8a'
old_manifest = json.loads(old_manifest_bytes)
summary = json.loads((ROOT / 'run-001/qualification.json').read_text(encoding='utf-8'))
assert summary['status'] == 'SYNTHETIC_ONLY_PASS' and summary['case_count'] == 3
for name, expected in summary['source_hashes'].items():
    assert sha((ROOT / name).read_bytes()) == expected
for name in ('owned_job.py', 'cooperative_producer.py', 'cooperative_consumer.py'):
    assert sha((ROOT / name).read_bytes()) == old_manifest['files'][name]['sha256']
old = (PREVIOUS / 'protected_pty.py').read_text(encoding='utf-8')
new = (ROOT / 'protected_pty.py').read_text(encoding='utf-8')
expected = old.replace("progress.update(producer_started=True, possible_effect=True,\n                    producer=job_identity(spec['job_name'], pty.pid))",
                       "progress.update(producer_started=True, possible_effect=True)\n    progress['producer'] = job_identity(spec['job_name'], pty.pid)")
expected = expected.replace("consumer_start_count=1, producer_alive_at_consumer_start=alive,\n                                    consumer=job_identity(spec['job_name'], consumer.pid))",
                            "consumer_start_count=1, producer_alive_at_consumer_start=alive)\n                    progress['consumer'] = job_identity(spec['job_name'], consumer.pid)")
assert expected == new, 'unexpected helper delta'
(ROOT / 'helper.diff').write_text(''.join(difflib.unified_diff(old.splitlines(keepends=True), new.splitlines(keepends=True),
                                fromfile='v3/protected_pty.py', tofile='v4/protected_pty.py')), encoding='utf-8')
files = ['protected_pty.py', 'owned_job.py', 'cooperative_producer.py', 'cooperative_consumer.py', 'qualify.py',
         'README.md', 'curate.py', 'helper.diff', 'run-001/qualification.json']
files += ['run-001/result-' + case['case'] + '.json' for case in summary['cases']]
entries = {}
def copy(payload, name):
    assert not re.search(rb'nxs_[0-9a-f]{48}', payload), name
    destination = PUBLIC / name
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(payload)
    entries[name] = {'sha256': sha(payload), 'bytes': len(payload)}
for name in files:
    copy((ROOT / name).read_bytes(), name)
for name in list(old_manifest['files']) + ['artifact-manifest.json']:
    payload = (PREVIOUS / name).read_bytes()
    if name in old_manifest['files']:
        assert sha(payload) == old_manifest['files'][name]['sha256']
    copy(payload, 'history-public-v3/' + name)
manifest = {'schema_version': 1, 'revision': 4, 'status': 'SYNTHETIC_ONLY_QUALIFIED', 'files': entries,
            'current_case_count': 3, 'historical_v3_case_count': 7, 'product_cli_calls': 0,
            'limit': 'Two injected boundary models plus one real benign ConPTY transfer; no product CLI/service qualification.'}
path = PUBLIC / 'artifact-manifest.json'
path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
assert {p.relative_to(PUBLIC).as_posix() for p in PUBLIC.rglob('*') if p.is_file()} == set(entries) | {'artifact-manifest.json'}
print(json.dumps({'public': str(PUBLIC), 'payloads': len(entries), 'manifest_sha256': sha(path.read_bytes()),
                  'helper_sha256': entries['protected_pty.py']['sha256'],
                  'qualification_sha256': entries['run-001/qualification.json']['sha256']}))
