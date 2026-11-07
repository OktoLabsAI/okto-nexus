"""Finite public allowlist; never copy case homes, raw streams or environments."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import zipfile

ROOT = Path(__file__).parent
PUBLIC = ROOT / 'public-v2'
PUBLIC.mkdir()
sha = lambda data: hashlib.sha256(data).hexdigest()
dependency = json.loads((ROOT / 'dependency.json').read_text(encoding='utf-8'))
wheel = ROOT / dependency['wheel']
assert sha(wheel.read_bytes()) == dependency['sha256']
rows = {}
with zipfile.ZipFile(wheel) as archive:
    for name in archive.namelist():
        if name.startswith('winpty/') and not name.endswith('/'):
            packed = archive.read(name)
            installed = ROOT / 'venv/Lib/site-packages' / name
            assert installed.read_bytes() == packed
            rows[name] = {'sha256': sha(packed), 'bytes': len(packed)}
SITE = Path('C:/Users/jpamb/AppData/Local/Temp/m1-observation-hosts-ai03jk1l/venv/Lib/site-packages')
functions = {}
for relative in ('okto_nexus/adapters/inbound/cli/remote_setup_io.py',
                 'okto_nexus/domain/keys.py',
                 'okto_nexus_connector/identity/import_flow.py'):
    payload = (SITE / relative).read_bytes()
    functions[relative] = {'sha256': sha(payload), 'bytes': len(payload), 'path': str(SITE / relative)}
proof = {'status': 'MATCH', 'wheel': dependency, 'package_payload_count': len(rows),
         'package_payloads': rows, 'installed_function_sources': functions,
         'limit': 'Focused dependency/function input proof, not a replacement for the host package proof.'}
(ROOT / 'dependency-proof.json').write_text(json.dumps(proof, indent=2), encoding='utf-8')
allowlist = ['README.md', 'protected_pty.py', 'owned_job.py', 'producer.py', 'consumer.py',
             'product_producer.py', 'product_consumer.py', 'qualify.py', 'prepare.py', 'prepare.log',
             'dependency.json', 'dependency-proof.json', 'curate.py']
allowlist += [f'run-{i:03d}/result-normal.json' for i in (1, 2, 3)]
for run in (4, 5, 6):
    allowlist += [f'run-{run:03d}/qualification.json']
    modes = ('normal', 'ambiguous', 'hang') + (('installed-functions',) if run >= 5 else ())
    allowlist += [f'run-{run:03d}/result-{mode}.json' for mode in modes]
allowlist += ['history-first-success/' + name for name in ('protected_pty.py', 'owned_job.py', 'qualify.py')]
entries = {}
for relative in allowlist:
    source = ROOT / relative
    payload = source.read_bytes()
    assert not re.search(rb'nxs_[0-9a-f]{48}', payload), relative
    destination = PUBLIC / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    entries[relative] = {'sha256': sha(payload), 'bytes': len(payload)}
previous = ROOT / 'public'
previous_manifest = json.loads((previous / 'artifact-manifest.json').read_text(encoding='utf-8'))
for relative in list(previous_manifest['files']) + ['artifact-manifest.json']:
    payload = (previous / relative).read_bytes()
    if relative in previous_manifest['files']:
        assert sha(payload) == previous_manifest['files'][relative]['sha256']
    assert not re.search(rb'nxs_[0-9a-f]{48}', payload), relative
    target = 'history-public-v1/' + relative
    destination = PUBLIC / target
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(payload)
    entries[target] = {'sha256': sha(payload), 'bytes': len(payload)}
manifest = {'schema_version': 1, 'status': 'SYNTHETIC_ONLY_QUALIFIED',
            'files': entries, 'native_product_cli_calls': 0, 'real_credentials': 0,
            'limit': 'No full connect lifecycle or service containment qualification; only synthetic children and direct installed sink/parser functions.'}
manifest_path = PUBLIC / 'artifact-manifest.json'
manifest_path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
assert {str(p.relative_to(PUBLIC)).replace('\\', '/') for p in PUBLIC.rglob('*') if p.is_file()} == set(entries) | {'artifact-manifest.json'}
print(json.dumps({'public': str(PUBLIC), 'payloads': len(entries), 'manifest_sha256': sha(manifest_path.read_bytes()),
                  'helper_sha256': entries['protected_pty.py']['sha256'],
                  'job_sha256': entries['owned_job.py']['sha256'],
                  'final_qualification_sha256': entries['run-006/qualification.json']['sha256'],
                  'dependency_payloads': len(rows)}))
