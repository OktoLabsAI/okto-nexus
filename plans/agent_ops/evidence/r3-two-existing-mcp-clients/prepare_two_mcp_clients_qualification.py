from pathlib import Path
import hashlib,json,sys
import xml.etree.ElementTree as ET

root=Path('C:/Users/jpamb/AppData/Local/Temp/r3-cooperative-drain-09ucmgsr')
repo=Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
assert len(sys.argv)==5, 'final source XML, source SHA, exact client selector JSON and capability report required'
report=Path(sys.argv[1])
cases=list(ET.parse(report).iter('testcase'))
assert len(cases)==1 and all(cases[0].find(tag) is None for tag in ('error','failure','skipped'))
name='tests/execution_r4/test_two_existing_mcp_clients.py'
source=repo/name
assert hashlib.sha256(source.read_bytes()).hexdigest()==sys.argv[2]
assert (repo/'tests/execution_r4/test_service_restart_contracts.py').read_bytes()==(root/'nexus-source-v1/tests/execution_r4/test_service_restart_contracts.py').read_bytes()
selector_path=Path(sys.argv[3])
selectors=json.loads(selector_path.read_text(encoding='utf-8'))
capability_path=Path(sys.argv[4])
capabilities=json.loads(capability_path.read_text(encoding='utf-8'))
for item in capabilities['inputs']:
    assert hashlib.sha256(Path(item['path']).read_bytes()).hexdigest()==item['sha256']
assert set(selectors)=={'NEXUS_AC03_NODE','NEXUS_AC03_INSPECTOR_ROOT','NEXUS_AC03_PYTHON','NEXUS_AC03_PYTHON_PATHS'}
assert all(isinstance(value,str) for value in selectors.values())
for key,value in selectors.items():
    if key.endswith('_PATHS'):
        assert all(Path(path).is_dir() for path in json.loads(value))
    else:
        assert Path(value).exists()
snapshot=root/'nexus-source-v1'/name
assert not snapshot.exists()
snapshot.write_bytes(source.read_bytes())
script=(root/'qualify_nexus.py').read_text(encoding='utf-8')
start=script.index('selected=')
end=script.index('\nproof={}',start)
checks = "\nfor item in client_inputs:\n    assert hashlib.sha256(Path(item['path']).read_bytes()).hexdigest()==item['sha256'], item['path']\n"
script=script[:start]+f'env.update({selectors!r})\nclient_inputs={capabilities["inputs"]!r}'+checks+f'selected=[{name!r}]'+script[end:]
script=script.replace("out=root/'nexus-installed-v1'", "out=root/'nexus-two-existing-mcp-clients'")
script=script.replace("print(json.dumps({'exit':result.returncode", checks+"(out/'external-client-proof.json').write_text(json.dumps(dict(selected_client_modules=client_inputs,unchanged_before_and_after=True,full_transitive_lock_claim=False),indent=2)+'\\n')\nprint(json.dumps({'exit':result.returncode")
(root/'qualify_two_mcp_clients.py').write_text(script,encoding='utf-8')
(root/'two-mcp-source-proof.json').write_text(json.dumps(dict(test=name,source_sha256=sys.argv[2],
    source_report=str(report),source_report_sha256=hashlib.sha256(report.read_bytes()).hexdigest(),
    selectors=selectors,selector_sha256=hashlib.sha256(selector_path.read_bytes()).hexdigest(),
    scope='Client code dependencies only; credentials remain synthetic and in private stdin; no provider'),indent=2)+'\n')
print(json.dumps(dict(prepared=True,source_cases=1,installed_run_started=False)))
