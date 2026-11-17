OUTPUT='C:\\Users\\jpamb\\AppData\\Local\\Temp\\nexus-qc36-installed-rilplc1y\\reports'
EXPECTED_PREFIX='C:\\Users\\jpamb\\AppData\\Local\\Temp\\nexus-qc-r1-package-i4u7k1l1\\venv'
import importlib,json,pathlib,sys,time
import pytest
OUT=pathlib.Path(OUTPUT)
PREFIX=pathlib.Path(EXPECTED_PREFIX).resolve()
COLLECTED=[]
FINISHED=[]
def verify(stage):
    names=('okto_nexus','nexus_connector_core','okto_nexus_connector')
    origins={n:importlib.import_module(n).__file__ for n in names}
    assert all(pathlib.Path(p).resolve().is_relative_to(PREFIX) for p in origins.values()),origins
    loaded={n:getattr(m,'__file__',None) for n,m in list(sys.modules.items()) if any(n==p or n.startswith(p+'.') for p in names)}
    assert all(not p or pathlib.Path(p).resolve().is_relative_to(PREFIX) for p in loaded.values()),loaded
    (OUT/('origins-'+stage+'.json')).write_text(json.dumps(dict(origins=origins,loaded=loaded,sys_path=sys.path,prefix=sys.prefix,isolated=sys.flags.isolated,dont_write_bytecode=sys.dont_write_bytecode,stdin_isatty=sys.stdin.isatty()),indent=2))
def pytest_sessionstart(session): verify('start')
def pytest_collection_finish(session):
    COLLECTED.extend(item.nodeid for item in session.items)
    (OUT/'collected.json').write_text(json.dumps(COLLECTED,indent=2))
def pytest_runtest_logfinish(nodeid,location): FINISHED.append(nodeid)
def pytest_sessionfinish(session,exitstatus):
    verify('end')
    (OUT/'inventory.json').write_text(json.dumps(dict(exitstatus=int(exitstatus),collected=COLLECTED,finished=FINISHED,not_run=[n for n in COLLECTED if n not in set(FINISHED)]),indent=2))
@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item,call):
    outcome=yield
    report=outcome.get_result()
    value=dict(nodeid=report.nodeid,phase=report.when,outcome=report.outcome,duration=report.duration)
    if report.failed: value['longrepr']=report.longreprtext
    with (OUT/'phases.jsonl').open('a',encoding='utf-8') as f: f.write(json.dumps(value)+'\n')

@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    if item.nodeid.split('::')[-1] != 'test_metadata_hint_is_not_an_identity_or_root_selector':
        yield
        return
    from okto_nexus.adapters.outbound import git_project_hint
    original = git_project_hint.discover_project_name
    def observe(*args, **kwargs):
        started = time.perf_counter()
        result = original(*args, **kwargs)
        record = dict(nodeid=item.nodeid, name=result.name, source=result.source,
            status=result.status, reason=result.reason,
            duration_seconds=time.perf_counter()-started,
            behavior='identical result object returned; no arguments or settings modified')
        with (OUT/'git-hint-observation.jsonl').open('a',encoding='utf-8') as stream:
            stream.write(json.dumps(record)+'\n')
        return result
    git_project_hint.discover_project_name = observe
    try:
        yield
    finally:
        git_project_hint.discover_project_name = original
