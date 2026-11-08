"""Bind prospective artifacts only. Never imports or installs any product."""
import ast
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).parent
DRAFT = ROOT / 'draft'
INSTALL = DRAFT / 'installation'
PROPOSAL = DRAFT / 'm1-codex-campaign-proposal-v9.json'
WHEEL = Path('C:/Users/jpamb/AppData/Local/Temp/m1-check-recovery-inopit5p/wheels/okto_nexus-0.3.3-py3-none-any.whl')
WHEEL_SHA = '99e1d530b27aeba7dcbd8adae8772ac19eaf4354ad5c31fdb80c0ed6e63d7680'

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')

def replace_assignment(text, name, value):
    matches = [n for n in ast.parse(text).body if isinstance(n, ast.Assign)
               and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name)
               and n.targets[0].id == name]
    assert len(matches) == 1
    node = matches[0]
    lines = text.splitlines(keepends=True)
    lines[node.lineno-1:node.end_lineno] = [name + ' = ' + repr(value) + '\n']
    return ''.join(lines)

assert sha(WHEEL) == WHEEL_SHA
p = json.loads(PROPOSAL.read_text(encoding='utf-8'))
assert p['revision'] == 9
assert not (ROOT / 'campaign').exists()
source_map_path = DRAFT / 'source-map.json'
sources = json.loads(source_map_path.read_text())
for name in ('m1_v9_lifecycle.py', 'supervisor_check.py', 'publication.py', 'response_loss.py'):
    source = Path(sources[name]['source'])
    assert (DRAFT / name).read_text() == source.read_text()
    (DRAFT / name).write_bytes(source.read_bytes())
report = json.loads((INSTALL / 'dependency-preparation.json').read_text())
assert report['status'] == 'DEPENDENCIES_ONLY_READY'
assert report['products_installed'] is False
assert report['dependency_files'] == 3209
assert sha(INSTALL / 'dependency-manifest.json') == report['dependency_manifest_sha256']

candidate = p['package_pins']['packages']['okto_nexus']
candidate.update(wheel=str(WHEEL), sha256=WHEEL_SHA,
                 qualified_reference_package=None,
                 qualification_status='PENDING_ROOT_INSTALLED_TESTS')
payloads = []
wheel_records = {}
for module, pin in p['package_pins']['packages'].items():
    wheel_path = Path(pin['wheel'])
    assert sha(wheel_path) == pin['sha256']
    with zipfile.ZipFile(wheel_path) as z:
        names = sorted(n for n in z.namelist() if n.startswith(module + '/') and not n.endswith('/'))
        assert len(names) == len(set(names))
        for name in names:
            parts = Path(name).parts
            assert '..' not in parts and not Path(name).is_absolute()
            payloads.append({'path': str(INSTALL / 'venv/Lib/site-packages' / name),
                             'sha256': hashlib.sha256(z.read(name)).hexdigest()})
    pin['files'] = pin['expected_payload_files'] = len(names)
    wheel_records[module] = {'wheel': str(wheel_path), 'sha256': pin['sha256'], 'files': len(names)}
assert len(payloads) == 982
p['package_pins']['files'] = payloads
p['package_pins']['payload_source'] = 'Prospective installed paths derived from exact wheel members; products remain absent here.'
p['package_pins']['status'] = 'PENDING_V9_NEXUS_QUALIFICATION'
installer_path = INSTALL / 'timed_install.py'
installer = installer_path.read_text(encoding='utf-8')
installer = replace_assignment(installer, 'WHEELS', wheel_records)
installer = replace_assignment(installer, 'EXPECTED_PAYLOAD_COUNT', len(payloads))
assert 'FINAL_PINS_BOUND = False' in installer
installer_path.write_text(installer, encoding='utf-8')
requirements = ''.join(Path(pin['wheel']).as_uri() + ' --hash=sha256:' + pin['sha256'] + '\n'
                       for pin in wheel_records.values())
(INSTALL / 'products-requirements.txt').write_text(requirements, encoding='utf-8')
install = p['base06_installation']
install.update(status='DEPENDENCIES_ONLY_READY_PRODUCTS_NOT_INSTALLED_NOT_AUTHORIZED',
               dependencies_prepared=True, products_installed=False,
               script_sha256=sha(installer_path),
               requirements_sha256=sha(INSTALL / 'products-requirements.txt'),
               dependency_manifest_sha256=report['dependency_manifest_sha256'],
               expected_payload_count=len(payloads),
               dependency_preparation=str(INSTALL / 'dependency-preparation.json'),
               dependency_preparation_sha256=sha(INSTALL / 'dependency-preparation.json'),
               direct_interpreter_qualification='PENDING_NEW_PREFIX_BENIGN_PID_PREFIX_PROBE',
               installer_enabled=False)
for label, path in [('timed_install', installer_path),
                    ('install_requirements', INSTALL / 'products-requirements.txt'),
                    ('install_dependency_manifest', INSTALL / 'dependency-manifest.json')]:
    p['execution_bundle']['files'][label] = {'path': str(path), 'sha256': sha(path)}
for entry in p['execution_bundle']['files'].values():
    if Path(entry['path']).is_relative_to(DRAFT):
        entry['sha256'] = sha(entry['path'])
p['execution_bundle']['qualification_scope'] = 'Static preparation and isolated dependency-only prefix proof; no v9 campaign or provider/native execution. Guards and modified controller qualification pending.'
p['status'] = 'DRAFT_AWAITING_PIN_QUALIFICATION_AND_APPROVAL'
write(PROPOSAL, p)
write(DRAFT / 'prospective-package-pins.json', {
    'status': 'CANDIDATE_NOT_YET_QUALIFIED', 'packages': wheel_records,
    'payload_count': len(payloads), 'prospective_installed_payloads': payloads,
    'product_install_executed': False, 'provider_or_service_executed': False,
    'root_qualification_pending': True,
})
for name, entry in sources.items():
    entry['sha256'] = sha(DRAFT / name)
    assert sha(entry['source']) == entry['source_sha256']
    if entry['reuse'] == 'byte_identical':
        assert entry['sha256'] == entry['source_sha256']
sources['installation/prepare_dependencies.py'] = {
    'source': 'C:/Users/jpamb/AppData/Local/Temp/m1-base06-install-g9ii2zhe/prepare_dependencies.py',
    'source_sha256': sha('C:/Users/jpamb/AppData/Local/Temp/m1-base06-install-g9ii2zhe/prepare_dependencies.py'),
    'sha256': sha(INSTALL / 'prepare_dependencies.py'),
    'reuse': 'only_removed_subprocess_probe_timeout30_root_derived_from_file',
}
write(source_map_path, sources)
initial = DRAFT / 'initial-static-checks.json'
if not initial.exists():
    initial.write_bytes((DRAFT / 'preparation-checks.json').read_bytes())
files = list(DRAFT.glob('*.py')) + list((DRAFT / 'controller').glob('*.py')) + list(INSTALL.glob('*.py'))
for path in files:
    compile(path.read_bytes(), str(path), 'exec')
write(DRAFT / 'preparation-checks.json', {
    'status': 'STATIC_AND_DEPENDENCIES_ONLY_PREPARATION',
    'compiled_files': [x.relative_to(DRAFT).as_posix() for x in files],
    'dependency_files_verified': 3209, 'environment_created': True,
    'dependency_preparation_sha256': sha(INSTALL / 'dependency-preparation.json'),
    'products_installed': False, 'timed_install_executed': False,
    'native_cli_calls': 0, 'provider_calls': 0, 'service_calls': 0, 'credential_reads': 0,
    'campaign_root_created': False, 'live_task_or_port_preflight': False,
    'tests_executed': 0, 'originals_unchanged': True,
    'reserves_cumulative': 9, 'confirmed_productive_history': 2,
    'predecessor_reserved_unconfirmed_productive': 1, 'new_maximum': 6,
    'confirmed_productive_maximum_if_all_new_confirmed': 8,
    'observed_tokens_carry_in': 45843, 'billing_final': False,
})
print(json.dumps({'status': 'DRAFT_CANDIDATE_BOUND_NO_INSTALL', 'payloads': len(payloads),
                  'proposal_sha256': sha(PROPOSAL), 'installer_sha256': sha(installer_path)}))
