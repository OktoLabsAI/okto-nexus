"""Read existing assertions/XML and compare existing payload files; no execution."""
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
OUT = Path(__file__).parent
BASE = '5545dbde'
TARGETS = {
    'tests/execution_r4/test_remote_terminal_setup.py': [
        'test_one_shot_key_never_enters_results_checkpoints_or_exported_handoff',
        'test_unexpected_secret_field_in_receipt_is_refused_without_checkpointing_it',
        'test_material_delivery_requires_tty_and_is_separate_from_public_stdout',
    ],
    'tests/execution_r4/test_participant_init.py': [
        'test_cli_never_falls_back_to_echoing_key',
        'test_malformed_http_errors_never_echo_response_or_key',
        'test_actual_http_redirect_does_not_forward_bearer',
    ],
    'tests/execution_r4/test_participant_launch.py': [
        'test_cli_does_not_echo_process_errors_or_secrets',
    ],
    'tests/test_observation_client.py': [
        'test_invalid_origins_are_sanitized_before_network',
    ],
}

def sha(data):
    return hashlib.sha256(data).hexdigest()

def frozen(path):
    return subprocess.check_output(['rtk', 'proxy', 'git', '-C', str(ROOT), 'show', f'{BASE}:{path}'])

result = {}
for path, names in TARGETS.items():
    source = frozen(path).decode('utf-8')
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names:
            segment = ast.get_source_segment(source, node)
            result[node.name] = {
                'source': path, 'line': node.lineno, 'end_line': node.end_lineno,
                'function_sha256': sha(segment.encode()),
                'assertions': [ast.unparse(n.test) for n in ast.walk(node) if isinstance(n, ast.Assert)],
                'retained_reports': [],
            }
for path in sorted((ROOT / 'plans/agent_ops/evidence').rglob('*.xml')):
    data = path.read_bytes()
    try:
        xml = ET.fromstring(data)
    except ET.ParseError:
        continue
    matching = {}
    for n in xml.iter('testcase'):
        name = n.attrib.get('name', '').split('[', 1)[0]
        if name not in result:
            continue
        identity = n.attrib.get('classname', '') + '::' + n.attrib.get('name', '')
        state = next((k for k in ('failure', 'error', 'skipped') if n.find(k) is not None), 'passed')
        matching.setdefault(name, []).append({'case_identity_sha256': sha(identity.encode()), 'state': state})
    for name, cases in matching.items():
        result[name]['retained_reports'].append({
            'path': path.relative_to(ROOT).as_posix(), 'sha256': sha(data),
            'cases': cases, 'passed': sum(c['state'] == 'passed' for c in cases),
            'failed_or_skipped': sum(c['state'] != 'passed' for c in cases),
        })

(OUT / 'protection-tests.json').write_text(json.dumps({'baseline': BASE, 'method': 'Source assertion inspection and existing JUnit XML parsing only. Reports overlap; counts are never added across reports. Case parameters are represented by identity digests; no token-bearing values copied.', 'tests': result}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({k: {'source': v['source'], 'line': v['line'], 'assertions': v['assertions'], 'passing_reports': [{'path': r['path'], 'passed': r['passed']} for r in v['retained_reports'] if r['passed']]} for k, v in result.items()}, ensure_ascii=False, indent=2))

proof = json.loads((ROOT / 'plans/agent_ops/evidence/pr04-participant-guide/installed/candidate-v1/package-proof.json').read_text())
installed = json.loads((ROOT / 'plans/agent_ops/evidence/r3-qualification-readiness/ci/ci/installed.json').read_text())
wheel = Path(proof['wheel'])
checks, extensions, migrations, static, resources = [], {}, [], [], []
with zipfile.ZipFile(wheel) as z:
    for path, expected in proof['files'].items():
        data = z.read('okto_nexus/' + path)
        source = ROOT / 'src/okto_nexus' / path
        destination = Path(installed['okto_nexus']['path']) / path
        checks.append({'path': path, 'proof_equals_wheel': sha(data) == expected, 'source_equals_wheel': source.read_bytes() == data, 'ci_install_equals_wheel': destination.read_bytes() == data})
        extensions[Path(path).suffix] = extensions.get(Path(path).suffix, 0) + 1
        if path.endswith('.sql'):
            migrations.append(path)
        elif '/static/' in path:
            static.append(path)
        elif not path.endswith('.py'):
            resources.append(path)
payload = {
    'method': 'Read-only bytes of existing wheel, current source and CI installation; no product imports or product process launched.',
    'wheel_sha256': sha(wheel.read_bytes()), 'expected_wheel_sha256': proof['wheel_sha256'],
    'files_checked': len(checks), 'extensions': extensions, 'migrations_count': len(migrations),
    'static_files': static, 'other_resources': resources,
    'mismatches': [x for x in checks if not all(v for k, v in x.items() if k != 'path')],
    'proof': 'plans/agent_ops/evidence/pr04-participant-guide/installed/candidate-v1/package-proof.json',
    'ci_installation_proof': 'plans/agent_ops/evidence/r3-qualification-readiness/ci/ci/installed.json',
}
(OUT / 'payload-verification.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(payload, ensure_ascii=False, indent=2))
