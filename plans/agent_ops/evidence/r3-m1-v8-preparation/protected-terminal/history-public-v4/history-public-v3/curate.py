import difflib
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).parent
BASE = ROOT.parent
PUBLIC = ROOT / 'public'
PUBLIC.mkdir()
sha = lambda payload: hashlib.sha256(payload).hexdigest()
summary = json.loads((ROOT / 'run-001/qualification.json').read_text(encoding='utf-8'))
assert summary['status'] == 'SYNTHETIC_ONLY_PASS' and len(summary['cases']) == 7
for name, expected in summary['source_hashes'].items():
    assert sha((ROOT / name).read_bytes()) == expected, name
previous = BASE / 'public-v2'
previous_manifest = json.loads((previous / 'artifact-manifest.json').read_text(encoding='utf-8'))
assert sha((previous / 'artifact-manifest.json').read_bytes()) == '5f18c982d43cc75c12cdb10dd28406916e0ef6d3f2f52c9cd4493d74a801e692'
proof = json.loads((previous / 'dependency-proof.json').read_text(encoding='utf-8'))
for name, expected in proof['package_payloads'].items():
    assert sha((BASE / 'venv/Lib/site-packages' / name).read_bytes()) == expected['sha256']
for name, expected in proof['installed_function_sources'].items():
    assert sha(Path(expected['path']).read_bytes()) == expected['sha256']
(ROOT / 'input-proof.json').write_text(json.dumps({'status': 'MATCH', 'dependency_and_installed_functions': proof,
    'final_sources': summary['source_hashes'], 'limit': 'Read-only input recheck; no new product package or campaign qualification.'}, indent=2), encoding='utf-8')
old = (previous / 'protected_pty.py').read_text(encoding='utf-8').splitlines(keepends=True)
new = (ROOT / 'protected_pty.py').read_text(encoding='utf-8').splitlines(keepends=True)
(ROOT / 'helper.diff').write_text(''.join(difflib.unified_diff(old, new, fromfile='v2/protected_pty.py', tofile='v3/protected_pty.py')), encoding='utf-8')
allowlist = ['protected_pty.py', 'owned_job.py', 'cooperative_producer.py', 'cooperative_consumer.py',
             'qualify.py', 'README.md', 'curate.py', 'input-proof.json', 'helper.diff', 'run-001/qualification.json']
allowlist += ['run-001/result-' + item['case'] + '.json' for item in summary['cases']]
entries = {}
def copy(payload, relative):
    assert not re.search(rb'nxs_[0-9a-f]{48}', payload), relative
    destination = PUBLIC / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(payload)
    entries[relative] = {'sha256': sha(payload), 'bytes': len(payload)}
for name in allowlist:
    copy((ROOT / name).read_bytes(), name)
for name in list(previous_manifest['files']) + ['artifact-manifest.json']:
    payload = (previous / name).read_bytes()
    if name in previous_manifest['files']:
        assert sha(payload) == previous_manifest['files'][name]['sha256']
    copy(payload, 'history-public-v2/' + name)
manifest = {'schema_version': 1, 'revision': 3, 'status': 'SYNTHETIC_ONLY_QUALIFIED', 'files': entries,
            'case_count': 7, 'product_cli_calls': 0, 'real_credentials': 0,
            'limit': 'No full remote connect lifecycle, external service ownership or productive-session qualification.'}
path = PUBLIC / 'artifact-manifest.json'
path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
assert {p.relative_to(PUBLIC).as_posix() for p in PUBLIC.rglob('*') if p.is_file()} == set(entries) | {'artifact-manifest.json'}
print(json.dumps({'public': str(PUBLIC), 'payloads': len(entries), 'manifest_sha256': sha(path.read_bytes()),
                  'helper_sha256': entries['protected_pty.py']['sha256'],
                  'qualification_sha256': entries['run-001/qualification.json']['sha256']}))
