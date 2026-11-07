import difflib
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

HERE = Path(__file__).parent
REPO = Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
BASE = REPO / 'plans/agent_ops/evidence/r3-m1-controller/preparation'
root_proof = Path('C:/Users/jpamb/AppData/Local/Temp/m1-drain-hosts-n7pm3omg/package-proof.json')
ancestry = json.loads((HERE / 'ancestry.json').read_text())
assert hashlib.sha256((REPO / ancestry['closure_path']).read_bytes()).hexdigest() == ancestry['closure_sha256']
for name, digest in ancestry['historical_files'].items():
    assert hashlib.sha256((BASE / name).read_bytes()).hexdigest() == digest
files = ['controller.py', 'token_collector.py', 'setup_journal.py', 'test_v8.py',
         'canonical_fixture.py', 'run_tests.py']
freeze = {name: hashlib.sha256((HERE / name).read_bytes()).hexdigest() for name in files}
# The earlier freeze is retained as preparation history, not claimed as final.
shutil.copy2(HERE / 'freeze.json', HERE / 'initial-freeze.json')
(HERE / 'freeze.json').write_text(json.dumps(freeze, indent=2), encoding='utf-8')
diff = ''.join(''.join(difflib.unified_diff((BASE / name).read_text().splitlines(True),
    (HERE / name).read_text().splitlines(True), fromfile='historical/' + name, tofile='v8/' + name))
    for name in ('controller.py', 'token_collector.py'))
(HERE / 'candidate.diff').write_text(diff, encoding='utf-8')
proof = json.loads(root_proof.read_text())
checked = {}
for package, info in proof.items():
    if package == 'imports': continue
    wheel = Path(info['wheel'])
    assert hashlib.sha256(wheel.read_bytes()).hexdigest() == info['sha256']
    with zipfile.ZipFile(wheel) as archive:
        names = [name for name in archive.namelist() if name.startswith(package + '/') and not name.endswith('/')]
        for name in names:
            path = Path(info['package']).parent / name
            assert path.read_bytes() == archive.read(name), name
    assert len(names) == info['files']
    checked[package] = {'wheel_sha256': info['sha256'], 'payloads_checked': len(names),
                        'wheel_equals_installed_after_tests': True}
(HERE / 'installed-post-proof.json').write_text(json.dumps(checked, indent=2), encoding='utf-8')
summary = {'status': 'PREPARATION_ONLY_NOT_AUTHORIZED', 'final_tests': 19, 'initial_tests': 15,
           'final_seconds': 5.60, 'failures': 0, 'errors': 0, 'skipped': 0,
           'initial_preserved': True, 'historical_sources_unchanged': True,
           'carry_in_admissions': 2, 'carry_in_observed_tokens': 45843,
           'max_new_admissions': 6, 'max_cumulative_admissions': 8,
           'proposed_cumulative_preventive_tokens': 200000, 'tolerance': 700000, 'deadline_seconds': 120,
           'approval_and_proposal_digest_required_before_dispatch': True,
           'real_campaign_admissions': 0, 'providers': 0, 'services': 0, 'credential_access': 0,
           'limit': 'Pure Core event translation + fake transports. No native/HTTP/provider qualification; no real authorization receipt.'}
(HERE / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
out = HERE / 'public'
out.mkdir(exist_ok=False)
allowlist = files + ['README.md', 'ancestry.json', 'freeze.json', 'initial-freeze.json',
                    'candidate.diff', 'summary.json', 'installed-post-proof.json', 'curate.py']
for stage in ('initial', 'final'):
    allowlist += [stage + '/' + name for name in ('stdout.log', 'tests.xml', 'result.json', 'inputs-before.json', 'imports.json')]
for name in allowlist:
    target = out / name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(HERE / name, target)
manifest = {'version': 1, 'status': 'PREPARATION_ONLY_NOT_AUTHORIZED', 'files': {
    name: {'sha256': hashlib.sha256((out / name).read_bytes()).hexdigest(), 'bytes': (out / name).stat().st_size}
    for name in sorted(allowlist)}}
(out / 'artifact-manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
print(json.dumps({'path': str(out), 'payloads': len(allowlist),
    'manifest_sha256': hashlib.sha256((out / 'artifact-manifest.json').read_bytes()).hexdigest(),
    'controller_sha256': freeze['controller.py'], 'collector_sha256': freeze['token_collector.py']}))
