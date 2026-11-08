"""Public allowlist only; no case homes, raw PTY streams, material or venv."""
import ast
import difflib
import hashlib
import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
OLD = Path('C:/Users/jpamb/AppData/Local/Temp/m1-protected-pty-j_c21e97/revision-5')
PUBLIC = ROOT / 'public'
PUBLIC.mkdir(exist_ok=False)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(name, value):
    (PUBLIC / name).write_bytes((json.dumps(value, indent=2) + '\n').encode())


def copy(source, name):
    target = PUBLIC / name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)


source_names = ('protected_pty.py', 'owned_job.py', 'marker_producer.py', 'marker_consumer.py',
                'test_pty_gates.py', 'qualify.py', 'pytest.ini', 'README.md', 'curate.py')
for name in source_names:
    copy(ROOT / name, name)
attempts = {}
successful_final = set()
for attempt in ('attempt-001', 'attempt-002', 'attempt-003'):
    path = ROOT / attempt
    before = json.loads((path / 'inputs-before.json').read_text())
    after = json.loads((path / 'inputs-after.json').read_text())
    assert before == after
    nodes = list(ET.parse(path / 'tests.xml').iter('testcase'))
    passed = [node for node in nodes if not any(c.tag in ('failure', 'error', 'skipped') for c in node)]
    failed = [node for node in nodes if node.find('failure') is not None]
    assert not any(node.find('error') is not None or node.find('skipped') is not None for node in nodes)
    if attempt != 'attempt-001':
        assert before['sources']['protected_pty.py'] == sha(ROOT / 'protected_pty.py')
        successful_final.update((n.attrib['classname'], n.attrib['name']) for n in passed)
    records = []
    for source in sorted((path / 'cases').glob('*-result.json')):
        result = json.loads(source.read_text())
        assert result['active_job_processes_after'] == 0 and result['public_ipc_readers_joined']
        assert result['worker_exit'] is not None
        records.append({'file': source.name, 'status': result['status'],
                        'forced_auxiliary_cleanup': result['forced_owned_cleanup']})
        copy(source, attempt + '/results/' + source.name)
    for name in ('inputs-before.json', 'inputs-after.json', 'imports.json', 'stdout.txt', 'stderr.txt',
                 'tests.xml', 'result.json', 'process.json'):
        copy(path / name, attempt + '/' + name)
    for source in sorted((path / 'source').glob('*.py')):
        copy(source, attempt + '/source/' + source.name)
    attempts[attempt] = {'passed': len(passed), 'failed': len(failed), 'inputs_unchanged': True,
                          'helper_sha256': before['sources']['protected_pty.py'], 'results': records}
assert len(successful_final) == 20
# Only the previously failed fixture timeout changed after the 19 passes.
def functions(path):
    return {n.name: ast.dump(n, include_attributes=False) for n in ast.parse(path.read_text()).body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
prior = functions(ROOT / 'attempt-002/source/test_pty_gates.py')
current = functions(ROOT / 'test_pty_gates.py')
assert [name for name in prior if prior[name] != current[name]] == [
    'test_missing_handoff_marker_expires_without_consumer_gate_or_delivery']
diff = ''.join(difflib.unified_diff((OLD / 'protected_pty.py').read_text().splitlines(keepends=True),
    (ROOT / 'protected_pty.py').read_text().splitlines(keepends=True),
    fromfile='v5/protected_pty.py', tofile='v10/protected_pty.py'))
(PUBLIC / 'helper.diff').write_bytes(diff.encode())
qualification = {
    'status': 'SYNTHETIC_GATED_PTY_QUALIFIED', 'helper_path': str(ROOT / 'protected_pty.py'),
    'helper_sha256': sha(ROOT / 'protected_pty.py'), 'owned_job_sha256': sha(ROOT / 'owned_job.py'),
    'v5_sha256_unchanged': sha(OLD / 'protected_pty.py'),
    'v5_owned_job_bytes_identical': (OLD / 'owned_job.py').read_bytes() == (ROOT / 'owned_job.py').read_bytes(),
    'qualified_final_helper_unique_cases': 20, 'qualified_case_nodes': sorted('::'.join(n) for n in successful_final),
    'attempts': attempts,
    'first_failure': 'Synthetic import probe used PTY.__module__, which did not expose the extension __file__; corrected to the actually imported winpty.winpty module before gates.',
    'second_failure': 'Four-second synthetic fixture expired before producer initialization, so it did not reach missing-handoff condition. Preserved; only that fixture repeated at15s, with helper/operational deadline unchanged.',
    'second_to_third_test_ast_delta_only': 'test_missing_handoff_marker_expires_without_consumer_gate_or_delivery',
    'pywinpty': {'version': '3.0.3', 'site': str(OLD.parent / 'venv/Lib/site-packages'),
                'payloads_verified_before_after': 12},
    'native_product_cli_calls': 0, 'provider_calls': 0, 'real_credentials': 0, 'native_service_actions': 0,
    'installed_functions': ['remote_setup_io.material_sink', 'remote_setup_io.handoff_sink'],
    'limits': ['Synthetic Python children only; no real remote setup or M1 acceptance.',
        'The callback must be bounded by the shared deadline; helper cannot preempt arbitrary caller code.',
        'Gates do not cancel already-started effects and are not atomic with later OS scheduling.',
        'UNKNOWN never implies no prior material delivery; no replay is permitted.',
        'Forced cleanup owns auxiliary Job descendants only; it is not service force and cannot qualify TRANSFERRED_ONCE.',
        'Owner-side remote queue/poll/fence composition is qualified separately by its owner.'],
}
write('qualification.json', qualification)
files = {p.relative_to(PUBLIC).as_posix(): {'sha256': sha(p), 'bytes': p.stat().st_size}
         for p in sorted(PUBLIC.rglob('*')) if p.is_file()}
write('artifact-manifest.json', {'version': 1, 'files': files,
    'excluded': ['venv', 'case homes', 'raw terminal/consumer output', 'generated material', 'handoff fixtures']})
print(json.dumps({'public': str(PUBLIC), 'payloads': len(files),
    'manifest_sha256': sha(PUBLIC / 'artifact-manifest.json'),
    'qualification_sha256': sha(PUBLIC / 'qualification.json'),
    'helper_sha256': qualification['helper_sha256']}, indent=2))
