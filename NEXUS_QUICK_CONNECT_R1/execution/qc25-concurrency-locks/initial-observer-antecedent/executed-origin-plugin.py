
import importlib.util,json,pathlib,re,sys
import pytest
ROOT=pathlib.Path(__file__).resolve().parents[1]
PREFIX=pathlib.Path('C:\\Users\\jpamb\\AppData\\Local\\Temp\\nexus-qc-r1-package-t24_dnfc\\venv').resolve()
OUT=pathlib.Path(__import__('os').environ['QC_DERIVATIVE_OUTPUT'])

def pytest_sessionstart(session):
    origins={name:importlib.util.find_spec(name).origin for name in ('okto_nexus','nexus_connector_core','okto_nexus_connector')}
    assert all(pathlib.Path(value).resolve().is_relative_to(PREFIX) for value in origins.values()),origins
    assert not (ROOT/'src').exists()
    (OUT/'origins.json').write_text(json.dumps(dict(origins=origins,prefix=sys.prefix,sys_path=sys.path),indent=2))

def pytest_sessionfinish(session, exitstatus):
    origins={name:importlib.util.find_spec(name).origin for name in ('okto_nexus','nexus_connector_core','okto_nexus_connector')}
    invalid={name:getattr(module,'__file__',None) for name,module in list(sys.modules.items()) if name.startswith(('okto_nexus','nexus_connector_core','okto_nexus_connector')) and getattr(module,'__file__',None) and not pathlib.Path(module.__file__).resolve().is_relative_to(PREFIX)}
    assert not invalid,invalid
    (OUT/'origins-finish.json').write_text(json.dumps(dict(origins=origins,invalid=invalid),indent=2))

@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item,call):
    outcome=yield
    report=outcome.get_result()
    record=dict(nodeid=report.nodeid,when=report.when,outcome=report.outcome,duration=report.duration)
    if report.failed:
        text=report.longreprtext
        text=re.sub(r'(?:nxs_|nxsept_|nxc4_|nxt4_)[A-Za-z0-9_-]+','<ephemeral-token-redacted>',text)
        record['failure']=text
        if report.when=='call':
            (OUT/'failed-call.json').write_text(json.dumps(record,indent=2))
    with (OUT/'reports.jsonl').open('a') as f:
        f.write(json.dumps(record)+'\n')
    print('IMMEDIATE_REPORT '+json.dumps(record),flush=True)
