from pathlib import Path
import hashlib,json,sys
import xml.etree.ElementTree as ET

root=Path('C:/Users/jpamb/AppData/Local/Temp/r3-cooperative-drain-09ucmgsr')
repo=Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
assert len(sys.argv)==4, 'final two-case XML, participation SHA and cooperation SHA required'
report=Path(sys.argv[1])
cases=list(ET.parse(report).iter('testcase'))
assert len(cases)==2 and all(c.find(tag) is None for c in cases for tag in ('error','failure','skipped'))
files={
    'tests/execution_r4/test_two_existing_mcp_clients.py':sys.argv[2],
    'tests/execution_r4/test_two_existing_mcp_cooperation.py':sys.argv[3],
}
for name,sha in files.items():
    assert hashlib.sha256((repo/name).read_bytes()).hexdigest()==sha
assert (repo/'tests/execution_r4/test_service_restart_contracts.py').read_bytes()==(root/'nexus-source-v1/tests/execution_r4/test_service_restart_contracts.py').read_bytes()
previous=root/'nexus-source-v1/tests/execution_r4/test_two_existing_mcp_clients.py'
assert hashlib.sha256(previous.read_bytes()).hexdigest()=='1b8bee3d7601bcf7d9b7793af521cfd13e7a4f69ae8bb946943ad15b80c5429c'
assert not (root/'nexus-source-v1/tests/execution_r4/test_two_existing_mcp_cooperation.py').exists()
for name in files:
    (root/'nexus-source-v1'/name).write_bytes((repo/name).read_bytes())
script=(root/'qualify_two_mcp_clients.py').read_text(encoding='utf-8')
old="selected=['tests/execution_r4/test_two_existing_mcp_clients.py']"
assert script.count(old)==1
script=script.replace(old,'selected='+repr(list(files)))
script=script.replace("out=root/'nexus-two-existing-mcp-clients'", "out=root/'nexus-two-mcp-cooperation'")
(root/'qualify_mcp_cooperation.py').write_text(script,encoding='utf-8')
(root/'mcp-cooperation-source-proof.json').write_text(json.dumps(dict(source_report=str(report),
    source_report_sha256=hashlib.sha256(report.read_bytes()).hexdigest(),files=files,
    cases=[c.attrib for c in cases],new_case=1,requalified_participation_case=1,product_changed=False),indent=2)+'\n')
print(json.dumps(dict(prepared=True,source_cases=2,installed_run_started=False)))
