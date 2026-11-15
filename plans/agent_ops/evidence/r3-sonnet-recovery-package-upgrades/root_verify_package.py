"""Read-only package comparison; never imports application or reads credentials."""
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parent
PACKAGE = ROOT / 'package'
OLD = Path('C:/Users/jpamb/AppData/Local/Temp/m1-v12-bundle-bldo9qy7/successor14/work-revision16/package/installation.json')

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

manifest = json.loads((PACKAGE / 'installation.json').read_bytes())
provenance = json.loads((PACKAGE / 'build-provenance.json').read_bytes())
assert provenance['connector_commit'] == '28e8093997849ba47a018e5d4728f8b3535be4b1'
assert manifest['status'] == 'INSTALLED_VERIFIED'
prefix = (PACKAGE / 'venv').resolve()
assert Path(manifest['python_prefix']).resolve() == prefix
assert sha(PACKAGE / 'installation.json') == provenance['installed_manifest_sha256']
assert sha(OLD) == '3f78145bfa366d4b206712e825e5d4c8b35fce9579f721d798d16e7f19b3d155'
for item in manifest['files']:
    path = Path(item['path']).resolve()
    assert path.is_relative_to(prefix), 'payload outside selected prefix'
    assert sha(path) == item['sha256'], 'payload changed'
for name, pin in manifest['wheels'].items():
    assert sha(pin['path']) == pin['sha256'] == provenance['wheels'][name]
connector = manifest['wheels']['okto_nexus_connector-0.0.12-py3-none-any.whl']
compared = []
with zipfile.ZipFile(connector['path']) as wheel:
    for name in ('connect.py', 'connect_setup.py', 'identity.py'):
        relative = 'okto_nexus_connector/cli/commands/' + name
        source = PACKAGE / 'connector-source/src' / relative
        installed = prefix / 'Lib/site-packages' / relative
        assert source.read_bytes() == wheel.read(relative) == installed.read_bytes()
        compared.append(relative)
result = {
    'status': 'PASS_READ_ONLY_PACKAGE_COMPARISON',
    'installed_files_checked': len(manifest['files']),
    'changed_sources_equal_archive_wheel_installed': compared,
    'old_installation_manifest_unchanged': True,
    'installation_sha256': sha(PACKAGE / 'installation.json'),
    'provenance_sha256': sha(PACKAGE / 'build-provenance.json'),
    'functional_tests_claimed': False,
    'service_or_provider_actions': False,
}
with (ROOT / 'root-package-verification.json').open('x', encoding='utf-8') as stream:
    stream.write(json.dumps(result, indent=2) + '\n')
print(json.dumps(result))
