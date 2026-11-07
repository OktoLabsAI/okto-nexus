from pathlib import Path
import hashlib
import json
import sys
import xml.etree.ElementTree as ET

root = Path('C:/Users/jpamb/AppData/Local/Temp/r3-cooperative-drain-09ucmgsr')
repo = Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
assert len(sys.argv) == 5, 'restart XML, restart SHA, child XML, child SHA required'
inputs = [
    ('tests/execution_r4/test_service_restart_contracts.py', Path(sys.argv[1]), sys.argv[2], 3),
    ('tests/execution_r4/test_service_surviving_child.py', Path(sys.argv[3]), sys.argv[4], 1),
]
proof = []
for name, report, expected_sha, expected_count in inputs:
    cases = list(ET.parse(report).iter('testcase'))
    assert len(cases) == expected_count
    assert all(c.find(tag) is None for c in cases for tag in ('failure', 'error', 'skipped'))
    source = repo / name
    assert hashlib.sha256(source.read_bytes()).hexdigest() == expected_sha
    destination = root / 'nexus-source-v1' / name
    assert not destination.exists(), str(destination)
    proof.append(dict(test=name, sha256=expected_sha, source_report=str(report),
                      source_report_sha256=hashlib.sha256(report.read_bytes()).hexdigest(),
                      cases=[c.attrib for c in cases]))
helpers = ['tests/execution_r4/remote_renewal_helpers.py', 'tests/execution_r4/test_vertical_inventory.py']
for name in helpers:
    assert (repo/name).read_bytes() == (root/'nexus-source-v1'/name).read_bytes(), name
for name, _, _, _ in inputs:
    (root/'nexus-source-v1'/name).write_bytes((repo/name).read_bytes())
script = (root/'qualify_nexus.py').read_text(encoding='utf-8')
start = script.index('selected=')
end = script.index('\nproof={}', start)
script = script[:start] + 'selected=' + repr([item[0] for item in inputs]) + script[end:]
script = script.replace("out=root/'nexus-installed-v1'", "out=root/'nexus-service-restart-contracts'")
(root/'qualify_service_restart.py').write_text(script, encoding='utf-8')
(root/'service-restart-source-proof.json').write_text(json.dumps(dict(
    cases=proof, helpers={name: hashlib.sha256((repo/name).read_bytes()).hexdigest() for name in helpers},
    product_changes=False, scope='Current final source qualifications only; redirector-based proof excluded'),
    indent=2)+'\n', encoding='utf-8')
print(json.dumps(dict(prepared=True, source_cases=4, installed_run_started=False)))
