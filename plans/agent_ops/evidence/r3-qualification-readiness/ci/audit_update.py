from pathlib import Path
import hashlib
import json
import shutil
import zipfile

OUT = Path(__file__).parent
REPO = Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
CONNECTOR = Path('D:/Projetos/Techridy/okto-nexus-connector')
WHEEL = Path('C:/Users/jpamb/AppData/Local/Temp/remote-renewal-release-8hs8nezr/candidate-v2/wheels/okto_nexus_connector-0.0.12-py3-none-any.whl')
NEXUS = Path('C:/Users/jpamb/AppData/Local/Temp/dx04-mcp-guide-installed-sk13m28a/candidate-v1/wheels/okto_nexus-0.3.3-py3-none-any.whl')
EXPECTED_CONNECTOR = 'a8cf18105fa1cdca0443b6a3be08972d5576f72f3ce07e5a19dd9fc7cd59ae5a'
EXPECTED_CORE = '5721e462add21d65380f070a68db07a653a498a78d4be9ea0cf949909d3cfecb'
EXPECTED_NEXUS = '9b18dc0c69673bb730198ca461f2464c8ee4ae3fdc1226f22ffcb8140783412f'
digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
assert digest(WHEEL) == EXPECTED_CONNECTOR
assert digest(NEXUS) == EXPECTED_NEXUS
manifest_path = REPO/'vendor/ci/manifest.json'
manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
core, connector = manifest['artifacts']
assert core['sha256'] == EXPECTED_CORE and digest(REPO/core['path']) == EXPECTED_CORE
assert connector['path'] == 'vendor/ci/okto_nexus_connector-0.0.12-py3-none-any.whl'
rows = []
with zipfile.ZipFile(WHEEL) as archive:
    names = sorted(name for name in archive.namelist() if name.startswith('okto_nexus_connector/') and not name.endswith('/'))
    assert len(names) == 123, len(names)
    for name in names:
        source = CONNECTOR/'src'/name
        payload = archive.read(name)
        assert source.is_file() and source.read_bytes() == payload, name
        rows.append(dict(path=name, bytes=len(payload), sha256=hashlib.sha256(payload).hexdigest(), source_equal=True))
    metadata_name = next(name for name in archive.namelist() if name.endswith('.dist-info/METADATA'))
    metadata = archive.read(metadata_name).decode('utf-8')
    requirements = [line.removeprefix('Requires-Dist: ') for line in metadata.splitlines() if line.startswith('Requires-Dist: ')]
shutil.copyfile(manifest_path, OUT/'manifest-before.json')
old_hash = connector['sha256']
shutil.copyfile(REPO/connector['path'], OUT/'connector-before.whl')
shutil.copyfile(WHEEL, REPO/connector['path'])
connector['sha256'] = EXPECTED_CONNECTOR
manifest_path.write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
assert digest(REPO/connector['path']) == EXPECTED_CONNECTOR
assert manifest['artifacts'][0] == core and digest(REPO/core['path']) == EXPECTED_CORE
report = dict(connector_commit='fb3fff473ff246adcffa9e91573ac85f7a394170',
    source=str(CONNECTOR/'src/okto_nexus_connector'), wheel=str(WHEEL),
    previous_connector_sha256=old_hash, connector_sha256=EXPECTED_CONNECTOR,
    core_sha256=EXPECTED_CORE, nexus_sha256=EXPECTED_NEXUS,
    package_file_count=len(rows), all_source_files_equal=True, package_files=rows,
    connector_requires_dist=requirements,
    changed_checkout_files=[connector['path'],'vendor/ci/manifest.json'])
(OUT/'wheel-source-proof.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k not in ('package_files','connector_requires_dist')},indent=2))
