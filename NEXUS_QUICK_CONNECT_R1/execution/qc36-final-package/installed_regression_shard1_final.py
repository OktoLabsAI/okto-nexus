"""Prepared strict installed runner. Requires explicit package READY and selection.

Copies repository test helpers only, never src. It does not rewrite test bodies or
subprocess argv; parent pytest origins are guarded, nested-child provenance must
be reviewed separately where a selected test launches an application process.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import time
import tomllib
import zipfile

import psutil

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]
spec=importlib.util.spec_from_file_location('qc36_builder',HERE/'package.py')
builder=importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)

GUARD='''import importlib,json,pathlib,sys,time
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
    with (OUT/'phases.jsonl').open('a',encoding='utf-8') as f: f.write(json.dumps(value)+'\\n')
'''

GUARD += "\n@pytest.hookimpl(hookwrapper=True)\ndef pytest_runtest_call(item):\n    if item.nodeid.split('::')[-1] != 'test_metadata_hint_is_not_an_identity_or_root_selector':\n        yield\n        return\n    from okto_nexus.adapters.outbound import git_project_hint\n    original = git_project_hint.discover_project_name\n    def observe(*args, **kwargs):\n        started = time.perf_counter()\n        result = original(*args, **kwargs)\n        record = dict(nodeid=item.nodeid, name=result.name, source=result.source,\n            status=result.status, reason=result.reason,\n            duration_seconds=time.perf_counter()-started,\n            behavior='identical result object returned; no arguments or settings modified')\n        with (OUT/'git-hint-observation.jsonl').open('a',encoding='utf-8') as stream:\n            stream.write(json.dumps(record)+'\\n')\n        return result\n    git_project_hint.discover_project_name = observe\n    try:\n        yield\n    finally:\n        git_project_hint.discover_project_name = original\n"

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--tests',nargs='+',required=True)
    parser.add_argument('--shard-index',type=int,default=0)
    parser.add_argument('--shard-count',type=int,default=1)
    parser.add_argument('--timeout',type=int,default=600)
    args=parser.parse_args()
    assert 0<=args.shard_index<args.shard_count and 1<=args.timeout<=3600
    package=Path(json.loads((HERE/'allocation.json').read_text())['root'])
    ready=json.loads((HERE/'READY.json').read_text())
    wheel=package/'artifacts/okto_nexus-0.3.6-py3-none-any.whl'
    assert ready['ready'] is True and hashlib.sha256(wheel.read_bytes()).hexdigest()==ready['wheel_sha256']
    prefix=package/'venv'
    root=Path(tempfile.mkdtemp(prefix='nexus-qc36-installed-'))
    for name in ['tree','cwd','tmp','reports','guard']:(root/name).mkdir()
    tree=root/'tree'
    shutil.copytree(REPO/'tests',tree/'tests',ignore=shutil.ignore_patterns('__pycache__','*.pyc','*.pyo'))
    assert not (tree/'src').exists()
    files=[]
    selectors={}
    for selection in args.tests:
        relative,separator,node=selection.partition('::')
        path=(tree/relative).resolve()
        assert path.is_relative_to(tree/'tests') and path.exists(),selection
        expanded=[path] if path.is_file() else sorted(path.rglob('test_*.py'))
        assert not separator or path.is_file()
        for item in expanded:
            files.append(item)
            selectors.setdefault(item,set()).add('::'+node if separator else '')
    files=sorted(set(files))
    selected=files[args.shard_index::args.shard_count]
    assert selected
    copied={str(p.relative_to(tree)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (tree/'tests').rglob('*') if p.is_file()}
    (root/'copied-tests.json').write_text(json.dumps(copied,indent=2)+'\n')
    sources=builder.pins()
    (root/'source-before.json').write_text(json.dumps(sources,indent=2)+'\n')
    def payload():
        result={}
        for artifact,module in [(wheel,'okto_nexus'),(REPO/'vendor/wheels/okto_nexus_connector_core-0.0.14-py3-none-any.whl','nexus_connector_core'),(REPO/'vendor/ci/okto_nexus_connector-0.0.13-py3-none-any.whl','okto_nexus_connector')]:
            with zipfile.ZipFile(artifact) as archive:
                for name in archive.namelist():
                    if name.startswith(module+'/') and not name.endswith('/'):
                        data=(prefix/'Lib/site-packages'/name).read_bytes()
                        assert data==archive.read(name),name
                        result[name]=hashlib.sha256(data).hexdigest()
        assert len(result)==1028  # QC36 wheel has 733 Nexus files, including quick_connect_render.py.
        return result
    before=payload()
    (root/'payload-before.json').write_text(json.dumps(before,indent=2)+'\n')
    guard='OUTPUT='+repr(str(root/'reports'))+'\nEXPECTED_PREFIX='+repr(str(prefix))+'\n'+GUARD
    (root/'guard/qc36_origin_guard.py').write_text(guard,encoding='utf-8')
    ini=root/'pytest.ini'
    markers=tomllib.loads((REPO/'pyproject.toml').read_text(encoding='utf-8'))['tool']['pytest']['ini_options'].get('markers',[])
    ini.write_text('[pytest]\nasyncio_mode=auto\nasyncio_default_fixture_loop_scope=function\nmarkers=\n'+''.join('    '+m+'\n' for m in markers))
    selected_arguments=[str(p)+suffix for p in selected for suffix in sorted(selectors[p])]
    pytest_args=['-p','qc36_origin_guard','-c',str(ini),'--rootdir='+str(tree),'--confcutdir='+str(tree),*selected_arguments,'-v','--tb=short','--junitxml='+str(root/'reports/tests.xml')]
    helper_paths=[str(root/'tree/tests'),*[str(p) for p in sorted((root/'tree/tests').rglob('*')) if p.is_dir() and any(p.glob('*.py'))]]
    code='import sys;sys.path[:0]='+repr([str(root/'guard'),*helper_paths])+';import pytest;raise SystemExit(pytest.main('+repr(pytest_args)+'))'
    argv=[str(prefix/'Scripts/python.exe'),'-I','-B','-X','utf8','-c',code]
    env=builder.environment(root)
    env.update(PATH=';'.join([str(prefix/'Scripts'),'C:/Python313','C:/Windows/System32','C:/Windows','C:/Program Files/Git/cmd']),GIT_CONFIG_GLOBAL=os.devnull,GIT_CONFIG_SYSTEM=os.devnull,GIT_CONFIG_NOSYSTEM='1')
    env['QC_DERIVATIVE_OUTPUT']=str(root/'reports')
    codex_home=root/'codex_home';codex_home.mkdir();env['CODEX_HOME']=str(codex_home)
    claude_home=root/'claude_config_dir_intentionally_absent'
    assert not claude_home.exists()
    env['CLAUDE_CONFIG_DIR']=str(claude_home)
    (root/'reports/runner-env-precondition.json').write_text(json.dumps(dict(
        CODEX_HOME=dict(path=env['CODEX_HOME'],exists=codex_home.exists()),
        CLAUDE_CONFIG_DIR=dict(path=env['CLAUDE_CONFIG_DIR'],exists=claude_home.exists()),
        HOME=env['HOME'],USERPROFILE=env['USERPROFILE'],
        account_or_provider_values_inherited=False),indent=2)+'\n')
    record=dict(started_at=datetime.now(timezone.utc).isoformat(),root=str(root),selected=[str(p.relative_to(tree)) for p in selected],argv=argv,cwd=str(root/'cwd'),helper_paths=helper_paths,stdin='closed PIPE; no NUL console reopening',timeout=args.timeout,signals=[])
    print(json.dumps(dict(status='START',root=str(root),selected=record['selected'])),flush=True)
    known={}
    with (root/'reports/stdout.log').open('w',encoding='utf-8') as log:
        process=subprocess.Popen(argv,cwd=root/'cwd',env=env,stdin=subprocess.PIPE,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
        process.stdin.close()
        deadline=time.monotonic()+args.timeout
        interrupted=None
        while process.poll() is None:
            try:
                parent=psutil.Process(process.pid)
                for child in [parent,*parent.children(recursive=True)]:
                    if child.pid not in known:known[child.pid]=dict(pid=child.pid,birth=child.create_time(),exe=child.exe())
            except psutil.NoSuchProcess:pass
            if time.monotonic()>deadline and interrupted is None:
                print(json.dumps(dict(status='SOFT_DEADLINE_REVIEW_REQUIRED',root=str(root),pid=process.pid)),flush=True)
                interrupted=time.monotonic()
            time.sleep(.25)
        record['exit_code']=process.wait(timeout=15)
    after=payload()
    source_after=builder.pins()
    record.update(ended_at=datetime.now(timezone.utc).isoformat(),payload_files=len(after),payload_drift=[p for p in before if before[p]!=after[p]],source_drift=[p for p in sources.keys()|source_after.keys() if sources.get(p)!=source_after.get(p)],known_processes=list(known.values()))
    (root/'payload-after.json').write_text(json.dumps(after,indent=2)+'\n')
    (root/'result.json').write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps(record),flush=True)
    raise SystemExit(record['exit_code'] or bool(record['payload_drift'] or record['source_drift']))

if __name__=='__main__':main()
