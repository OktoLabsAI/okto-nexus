import ast
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
ROOT = Path(json.loads((HERE / 'green-allocation.json').read_text())['root'])
OUT = HERE / 'green'
OUT.mkdir(exist_ok=True)
result = json.loads((ROOT / 'result.json').read_text())
assert not result['payload_drift']
assert all(not p['alive'] for case in result['cases'] for p in case['processes_after'])
start = json.loads((ROOT / 'source-pins-start.json').read_text())
end = json.loads((ROOT / 'source-pins-end.json').read_text())
scoped = ['src/okto_nexus/adapters/inbound/cli/connect.py', 'tests/quick_connect/test_qc35_review_cancel.py']
assert all(start[name] == end[name] for name in scoped)
nodes = []
sanitized = ET.Element('testsuite')
for test in ET.parse(ROOT / 'customization-cancel/junit.xml').iter('testcase'):
    failure = test.find('failure')
    error = test.find('error')
    failed = failure is not None or error is not None
    nodes.append({'name': test.attrib['name'], 'status': 'FAIL' if failed else 'PASS', 'seconds': test.attrib['time']})
    item = ET.SubElement(sanitized, 'testcase', test.attrib)
    if failed:
        ET.SubElement(item, 'failure', {'message': 'See retained sanitized call report; raw own fixture output remains in Temp.'})
ET.ElementTree(sanitized).write(OUT / 'junit-sanitized.xml', encoding='utf-8', xml_declaration=True)
for name in ['result.json', 'source-pins-start.json', 'source-pins-end.json', 'payload-start.json', 'payload-end.json']:
    shutil.copyfile(ROOT / name, OUT / name)
for name in ['runner.json', 'origins-start.json', 'origins-finish.json']:
    shutil.copyfile(ROOT / 'customization-cancel' / name, OUT / name)
test_path = REPO / scoped[1]
shutil.copyfile(test_path, OUT / 'test_qc35_review_cancel.py')
before = ast.parse((HERE.parent / 'test-lint/before/test_qc35_review_cancel.py').read_text(encoding='utf-8'))
after = ast.parse(test_path.read_text(encoding='utf-8'))
original_functions = {node.name: ast.dump(node) for node in before.body if isinstance(node, ast.FunctionDef)}
current_functions = {node.name: ast.dump(node) for node in after.body if isinstance(node, ast.FunctionDef)}
assert all(current_functions[name] == value for name, value in original_functions.items())
ruff_argv = ['rtk', 'proxy', 'ruff', 'check', '--isolated', '--select', 'E4,E7,E9,F', scoped[1]]
ruff = subprocess.run(ruff_argv, cwd=REPO, capture_output=True, text=True, timeout=30)
(OUT / 'ruff.txt').write_text(ruff.stdout + ruff.stderr)
assert ruff.returncode == 0
report = {'mode': 'SOURCE_ONLY_PR27_DEPENDENCIES_NOT_FINAL_INSTALLED', 'status': 'PASS' if all(node['status'] == 'PASS' for node in nodes) else 'FAIL',
    'nodes': nodes, 'passed': sum(node['status'] == 'PASS' for node in nodes), 'failed': sum(node['status'] == 'FAIL' for node in nodes),
    'payload_files': result['payload_files'], 'payload_drift': [], 'global_source_drift': result['repository_input_drift'],
    'scoped_source_pins_start_end_equal': {name: start[name] for name in scoped},
    'original_test_function_bodies_unchanged': True, 'new_cases': ['Customize c', 'Customize empty', 'Customize picker EOF', 'Customize field EOF', 'Review EOF', 'Resume EOF'],
    'assertions': 'Honest canceled/lifecycle/metadata/effects state; exact prompt budgets; retained checkpoint bytes; no added canonical operations, grants, bindings, sessions, Test or probes. Resume uses same configured profile and no replay.',
    'all_owned_processes_exited': True, 'signals': result['cases'][0]['signals'], 'provider_calls': 0,
    'ruff_argv': ruff_argv, 'ruff_exit': ruff.returncode,
    'limits': ['Source-only qualification against explicit checkout Nexus, with installed PR27 Core/Connector dependencies. Not the forthcoming final installed wheel.', 'Presentation modules may change independently during this cut; scoped connect/test pins must remain stable.', 'Original red cut remains preserved separately: two existing passes and six new failures.']}
(OUT / 'qualification.json').write_text(json.dumps(report, indent=2))
print(json.dumps({'passed': report['passed'], 'failed': report['failed'], 'global_source_drift': report['global_source_drift'], 'report_sha256': hashlib.sha256((OUT / 'qualification.json').read_bytes()).hexdigest()}))
