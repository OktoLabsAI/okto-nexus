"""Curated qualification metadata only; no private product/auth state copied."""
from pathlib import Path
import hashlib
import json
import xml.etree.ElementTree as ET

BASE = Path(__file__).resolve().parent
REPO = Path('D:/Projetos/Techridy/okto-nexus-connector')
CORE = Path('D:/Projetos/Techridy/okto-nexus-connector-core')
sha = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
sources = ['docs/service-lifecycle.md', 'src/okto_nexus_connector/daemon/lifecycle.py',
    'src/okto_nexus_connector/daemon/service_process.py', 'src/okto_nexus_connector/daemon/service_supervisor.py',
    'src/okto_nexus_connector/platform/user_service.py', 'src/okto_nexus_connector/platform/service_supervision.py',
    'src/okto_nexus_connector/service_upgrade.py', 'tests/unit/test_bounded_service_supervisor.py',
    'tests/unit/test_user_service_lifecycle.py']
runs = {}
for name in ['source-initial.xml', 'source-regression-initial.xml', 'source-regression-final.xml',
             'handshake-initial.xml', 'source-handshake-final.xml']:
    suite = ET.parse(BASE / name).getroot().find('testsuite')
    runs[name] = {key: suite.attrib[key] for key in ('tests', 'failures', 'errors', 'skipped', 'time')}
    runs[name]['sha256'] = sha(BASE / name)
assert runs['source-handshake-final.xml']['tests'] == '112'
assert runs['source-handshake-final.xml']['failures'] == runs['source-handshake-final.xml']['errors'] == '0'
projections = []
for path in sorted((BASE / 'pytest-handshake-final').glob('test_real_venv_redirector_*/connector/run/service-supervisor.json')):
    if not path.parents[2].name[-1].isdigit():
        continue  # pytest's "current" link aliases the last actual case
    value = json.loads(path.read_bytes())
    projection = {key: value[key] for key in ('parent', 'launcher', 'child', 'child_acknowledged',
        'child_exit_confirmed', 'launcher_exit_confirmed', 'launcher_exit_code', 'attempts_started', 'phase', 'last_exit_code')}
    projection.update(test_directory=path.parents[2].name, source_receipt_sha256=sha(path),
        benign_bootstrap_marker=(path.parent.parent / 'benign-bootstrap.json').exists(),
        no_service_or_provider_started=True)
    projections.append(projection)
assert len(projections) == 2
assert sorted(value['benign_bootstrap_marker'] for value in projections) == [False, True]
qualification = {'status': 'SOURCE_AND_BENIGN_PYTHON_HANDSHAKE_QUALIFIED_NOT_NATIVE_SERVICE_ACCEPTANCE',
    'repo': str(REPO), 'branch': 'feature/v0.0.12', 'commit': '42b73ca3fc95e1bcf10fb91976931369dd5229ea',
    'pushed': True, 'worktree_clean_after_commit': True,
    'sources': {name: sha(REPO / name) for name in sources},
    'core_dependencies': {name: sha(CORE / name) for name in (
        'src/nexus_connector_core/user_service_supervision.py', 'src/nexus_connector_core/user_service_definition.py')},
    'runner': {'python': 'C:/Users/jpamb/AppData/Local/Temp/r3-native-t19-t20-39ycaumc/venv/Scripts/python.exe',
        'flags': ['-I', '-B', '-X', 'utf8'], 'source_imports': [str(REPO / 'src'), str(CORE / 'src')],
        'mechanism': 'run_verified.py inserts the two source roots explicitly into sys.path; no PYTHONPATH and no editable/package install.',
        'shared_venv_mutated': False,
        'final_command': 'rtk proxy C:/Users/jpamb/AppData/Local/Temp/r3-native-t19-t20-39ycaumc/venv/Scripts/python.exe -I -B -X utf8 ' + str(BASE / 'run_verified.py'),
        'pytest_modules': ['tests/unit/test_bounded_service_supervisor.py', 'tests/unit/test_user_service_lifecycle.py',
            'tests/unit/test_service_upgrade.py', 'tests/unit/test_service_install.py'],
        'selector': 'not native_preflight_on_worker_thread', 'deselected': 1},
    'runs': runs,
    'antecedents': ['Initial expanded regression retained:94PASS/5FAIL. Five legacy-task fixtures incorrectly represented the new parent installation. They now explicitly preserve a legacy task/receipt, retain legacy read/stop coverage and require explicit policy migration for new start.',
        'The original direct-Popen-PID assumption passed injected tests but was invalid for the real Windows venv redirector. Final code uses two-writer nonce handshake, OS ancestry and both retained handles. The final112 cases supersede that assumption.',
        'Intermediate Ruff unused sys import removed; final Ruff passed.'],
    'final_checks': {'pytest_passed': 112, 'pytest_deselected': 1, 'ruff_errors': 0, 'git_diff_cached_check_exit': 0},
    'ruff_command': 'rtk proxy ruff check ' + ' '.join(name for name in sources if name.endswith('.py')),
    'benign_process_projections': projections,
    'scope': {'new_windows_tasks_started': 0, 'real_connector_services_started': 0, 'provider_calls': 0,
        'global_environment_or_personal_credentials_modified': False, 'shared_installed_payload_mutated': False,
        'runtime_claim_or_model_settlement_asserted': False, 'SVC_T19_promoted': False,
        'pending': 'Native Scheduler/crash/backoff/limit service campaign with newly built matching wheels.'}}
(BASE / 'qualification.json').write_text(json.dumps(qualification, indent=2) + '\n', encoding='utf-8')
names = list(runs) + ['qualification.json', 'run_tests.py', 'run_regressions.py', 'run_final.py',
    'run_handshake.py', 'run_verified.py', 'retain.py']
manifest = {'format': 'connector-bounded-supervisor-public-evidence-v1',
    'files': {name: {'sha256': sha(BASE / name), 'bytes': (BASE / name).stat().st_size} for name in names},
    'copiable_allowlist': names,
    'excluded': ['pytest temporary trees', 'raw service/handshake receipts and tokens', 'private auth/vault/state', 'installed environments']}
(BASE / 'public-allowlist.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'qualification_sha256': sha(BASE / 'qualification.json'),
    'public_allowlist_sha256': sha(BASE / 'public-allowlist.json'), 'files': len(names)}))
