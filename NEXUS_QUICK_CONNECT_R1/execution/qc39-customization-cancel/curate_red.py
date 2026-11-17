import hashlib
import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
ROOT = Path(json.loads((HERE / 'allocation.json').read_text())['root'])
OUT = HERE / 'red'
OUT.mkdir(exist_ok=True)
result = json.loads((ROOT / 'result.json').read_text())
assert not result['payload_drift']
assert all(not p['alive'] for case in result['cases'] for p in case['processes_after'])
start = json.loads((ROOT / 'source-pins-start.json').read_text())
end = json.loads((ROOT / 'source-pins-end.json').read_text())
assert start['src/okto_nexus/adapters/inbound/cli/connect.py'] == end['src/okto_nexus/adapters/inbound/cli/connect.py']
nodes = []
for test in ET.parse(ROOT / 'customization-cancel/junit.xml').iter('testcase'):
    failure = test.find('failure')
    nodes.append({'name': test.attrib['name'], 'status': 'FAIL' if failure is not None else 'PASS', 'failure': failure.attrib.get('message') if failure is not None else None})
for name in ['result.json', 'source-pins-start.json', 'source-pins-end.json', 'payload-start.json', 'payload-end.json']:
    shutil.copyfile(ROOT / name, OUT / name)
for name in ['runner.json', 'origins-start.json', 'origins-finish.json']:
    shutil.copyfile(ROOT / 'customization-cancel' / name, OUT / name)
shutil.copyfile(REPO / 'tests/quick_connect/test_qc35_review_cancel.py', OUT / 'test_qc35_review_cancel.py')
report = {'mode': 'SOURCE_ONLY_PR27_DEPENDENCIES_NOT_FINAL_INSTALLED', 'status': 'EXPECTED_RED', 'nodes': nodes,
    'passed': sum(node['status'] == 'PASS' for node in nodes), 'failed': sum(node['status'] == 'FAIL' for node in nodes),
    'payload_files': result['payload_files'], 'payload_drift': [], 'source_drift': result['repository_input_drift'],
    'connect_py_unchanged_during_red': True, 'connect_py_sha256': start['src/okto_nexus/adapters/inbound/cli/connect.py'],
    'all_owned_processes_exited': True, 'signals': result['cases'][0]['signals'], 'provider_calls': 0,
    'raw_log_preserved_temp_only': str(ROOT / 'customization-cancel/raw.log'),
    'limits': ['Two unrelated UI output Python modules changed during red; global source drift is explicitly nonzero.', 'Old existing two variants pass; four customization cancellations and two EOF prompts fail before the connect.py fix.']}
(OUT / 'qualification.json').write_text(json.dumps(report, indent=2))
source = (HERE / 'run_red.py').read_text(encoding='utf-8').replace("HERE / 'allocation.json'", "HERE / 'green-allocation.json'")
(HERE / 'run_green.py').write_text(source, encoding='utf-8')
print(json.dumps({'passed': report['passed'], 'failed': report['failed'], 'red_report_sha256': hashlib.sha256((OUT / 'qualification.json').read_bytes()).hexdigest()}))
