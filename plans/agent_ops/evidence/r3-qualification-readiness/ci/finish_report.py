from pathlib import Path
import hashlib
import importlib.metadata
import json
import xml.etree.ElementTree as ET
import zipfile

OUT = Path(__file__).parent
REPO = Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
read_json = lambda path: json.loads(path.read_text(encoding='utf-8'))
campaign = read_json(OUT/'ci/campaign.json')
assert campaign['status'] != 'RUNNING'
xml = ET.parse(OUT/'ci/tests.xml').getroot()
cases = list(xml.iter('testcase'))
failures = sum(case.find('failure') is not None or case.find('error') is not None for case in cases)
skipped = sum(case.find('skipped') is not None for case in cases)
renewal = [case for case in cases if 'test_remote_renewal' in case.attrib.get('classname','')]
proof = read_json(OUT/'wheel-source-proof.json')
installed = read_json(OUT/'ci/installed.json')
assert installed['okto_nexus_connector']['wheel_sha256'] == proof['connector_sha256']
assert installed['nexus_connector_core']['wheel_sha256'] == proof['core_sha256']
assert installed['okto_nexus']['wheel_sha256'] == proof['nexus_sha256']
assert len(renewal) == 4 and len(cases) == 8
manifest = read_json(REPO/'vendor/ci/manifest.json')
assert manifest['artifacts'][0]['sha256'] == proof['core_sha256']
assert manifest['artifacts'][1]['sha256'] == proof['connector_sha256']
for artifact in manifest['artifacts']:
    assert digest(REPO/artifact['path']) == artifact['sha256']
result = dict(status=campaign['status'], total_cases=len(cases), renewal_cases=len(renewal),
    narrow_ci_cases=len(cases)-len(renewal), failures=failures, skipped=skipped,
    changed_inputs=campaign['changed_inputs'], runner='tools/ci_installed.py test',
    exact_wheel_hashes={name:data['wheel_sha256'] for name,data in installed.items()},
    connector_package_files_compared=proof['package_file_count'], connector_source_equal=True,
    mcp_version='1.30.0', pip_check=read_json(OUT/'pip-check.json')['exit_code'],
    source_checkout_files_changed=proof['changed_checkout_files'],
    limitations=['Real loopback HTTP/IPC/WebSocket with synthetic native/provider fixtures.',
        'No personal vault, TLS/two-host, native-service or real-provider/M1 qualification.',
        'No source application import overrides or editable installation; installed runner verifies package payloads.'],
    evidence={name:digest(OUT/name) for name in ('wheel-source-proof.json','ci-runner.log','ci-runner.json',
        'ci/installed.json','ci/campaign.json','ci/tests.xml','pip-check.log','pip-check.json',
        'installed-metadata.json','installed-distributions.json')})
(OUT/'reports.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k != 'evidence'},indent=2))
