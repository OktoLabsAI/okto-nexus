"""Seal metadata and synthetic-fixture evidence; exclude session snapshots."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EVIDENCE = ROOT / 'evidence'
release_path = Path('C:/Users/jpamb/AppData/Local/Temp/pr09-installed-_p9t3pls/qualified-v2/package-proof.json')
release = json.loads(release_path.read_text())
relative_module = 'adapters/outbound/observation/herdr.py'
module = Path(release['installed_package']) / relative_module
assert hashlib.sha256(module.read_bytes()).hexdigest() == release['files'][relative_module]['installed_sha256']
proof = json.loads((EVIDENCE / 'namespace-proof.json').read_text())
assert proof['result'] == 'passed'
assert proof['secondary_stop']['all_owned_processes_exited']
assert proof['primary_alive_and_binding_unchanged_after_secondary_stop']
paths = [ROOT / name for name in ['prepare.py', 'qualify_namespace.py', 'collect_namespace.py',
    'config.toml', 'work/Fixture.cs', 'work/codex.exe']]
paths += sorted(path for path in EVIDENCE.iterdir() if path.is_file())
manifest = {'revision': 1, 'result': 'passed', 'scope': 'OBS-12 two explicit real Herdr namespaces with equal pane IDs',
    'package_proof': str(release_path), 'package_proof_sha256': hashlib.sha256(release_path.read_bytes()).hexdigest(),
    'wheel_sha256': release['wheel_sha256'], 'observer_module_sha256': hashlib.sha256(module.read_bytes()).hexdigest(),
    'runtime_session_snapshots_excluded': True, 'credentials_used': False, 'nexus_published': False,
    'primary_server_stopped': False, 'secondary_canonical_stop_and_children_exit': True,
    'artifacts': [{'path': str(path), 'bytes': path.stat().st_size,
        'sha256': hashlib.sha256(path.read_bytes()).hexdigest()} for path in paths]}
with (EVIDENCE / 'namespace-evidence-manifest.json').open('x', encoding='utf-8') as output:
    json.dump(manifest, output, indent=2)
print(json.dumps({'result': 'passed', 'artifact_count': len(paths),
    'manifest': str(EVIDENCE / 'namespace-evidence-manifest.json')}))
