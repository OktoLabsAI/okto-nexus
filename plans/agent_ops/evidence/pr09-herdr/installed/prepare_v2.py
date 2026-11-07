"""Prepare a second immutable release; do not execute build, install or tests."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent
build = (ROOT / 'build_release.py').read_text(encoding='utf-8')
build = build.replace("/ 'qualified'", "/ 'qualified-v2'")
build = build.replace('before = inventory(PACKAGE)', '''before = inventory(PACKAGE)
previous_path = ROOT.parent / 'qualified/package-proof.json'
previous = json.loads(previous_path.read_text(encoding='utf-8'))
previous_files = {name: item['source_sha256'] for name, item in previous['files'].items()}
assert set(before) == set(previous_files), 'Unexpected added/removed package files in the targeted V2 release.'
changed_files = sorted(name for name, digest in before.items() if digest != previous_files[name])
assert changed_files == ['adapters/outbound/observation/herdr.py'], changed_files
server_import_path = ROOT.parent / 'qualified/server-import-proof.json'
server_import = json.loads(server_import_path.read_text(encoding='utf-8'))
assert 'okto_nexus.adapters.outbound.observation.herdr' not in server_import['modules']
assert sha(Path(previous['wheel']).read_bytes()) == previous['wheel_sha256']''')
build = build.replace("(ROOT / 'package-proof.json').write_text", '''proof['previous_release'] = {
    'proof': str(previous_path), 'proof_sha256': sha(previous_path.read_bytes()),
    'wheel_sha256': previous['wheel_sha256'], 'changed_files': changed_files,
    'unchanged_file_count': len(before) - len(changed_files),
    'server_import_proof': str(server_import_path),
    'server_import_proof_sha256': sha(server_import_path.read_bytes()),
    'server_scope': 'The retained V1 Server does not import the changed optional observer CLI transport; every other package byte is identical.'}
(ROOT / 'package-proof.json').write_text''')
qualify = (ROOT / 'qualify_installed.py').read_text(encoding='utf-8')
qualify = qualify.replace("/ 'qualified'", "/ 'qualified-v2'")
qualify = qualify.replace('pr09-observation-installed-initial.xml', 'pr09-observation-installed-v2-initial.xml')
for name, source in [('build_release_v2.py', build), ('qualify_installed_v2.py', qualify)]:
    ast.parse(source, filename=name)
    with (ROOT / name).open('x', encoding='utf-8') as target:
        target.write(source)
print('V2 scripts prepared; no build/install/copy/test/server started.')
