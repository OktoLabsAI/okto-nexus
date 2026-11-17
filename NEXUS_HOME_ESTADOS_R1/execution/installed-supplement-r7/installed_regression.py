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
PACKAGE=HERE.parent/'package-hst-r7'
spec=importlib.util.spec_from_file_location('hst_builder',PACKAGE/'package.py')
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

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--tests',nargs='+',required=True)
    parser.add_argument('--shard-index',type=int,default=0)
    parser.add_argument('--shard-count',type=int,default=1)
    parser.add_argument('--timeout',type=int,default=600)
    args=parser.parse_args()
    assert 0<=args.shard_index<args.shard_count and 1<=args.timeout<=3600
    package=Path(json.loads((PACKAGE/'allocation.json').read_text())['root'])
    ready=json.loads((PACKAGE/'READY.json').read_text())
    frozen=json.loads((PACKAGE/'SOURCE_ASSET_READY.json').read_text())
    assert frozen['source_asset_ready'] is True and frozen['version']=='0.3.7'
    assert frozen==json.loads((package/'SOURCE_ASSET_READY.json').read_text()), 'Frozen gate drift'
    assert ready['source_commit']==frozen['source_commit']
    # Evidence/documentation commits may advance HEAD; product/test inputs may not.
    ancestor=subprocess.run(['rtk','proxy','git','merge-base','--is-ancestor',
        frozen['source_commit'],'HEAD'],cwd=REPO,
        input=b'',stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=15)
    assert ancestor.returncode==0, 'Frozen candidate must remain an ancestor of current HEAD'
    build=json.loads((package/'build-manifest.json').read_text())
    expected=dict(build['source_pins'])
    supplement=json.loads((HERE/'TESTS_READY.json').read_text())
    assert hashlib.sha256((HERE/'TESTS_READY.json').read_bytes()).hexdigest()=='9399da3f6f3c6bce562b6ef8ba5d6b5b66d864fdeb854abd6af646e78aedbe9c'
    assert len(expected)==1828 and supplement['expected_nodes']==7
    assert args.shard_count==1 and args.shard_index==0 and args.timeout==300
    source_report=REPO/'NEXUS_HOME_ESTADOS_R1'/supplement['source_qualification']
    assert hashlib.sha256(source_report.read_bytes()).hexdigest()==supplement['source_qualification_sha256']
    assert json.loads(source_report.read_text())['status']=='PASS_SOURCE_SCOPED'
    assert supplement['runtime_source_commit']==frozen['source_commit']
    assert supplement['runtime_wheel_sha256']==ready['wheel_sha256']
    assert args.tests==supplement['selections']
    # Exactly one new test file is allowed. No baseline source, frontend,
    # existing test, helper, lock or dependency byte may be replaced.
    assert set(supplement['additions'])=={'tests/home_states/test_final_boundaries_r7.py'}
    for name,pin in supplement['additions'].items():
        assert name not in expected and len(pin)==64
        expected[name]=pin
    required_inputs={'src/okto_nexus/adapters/outbound/sqlite/home_entries.py',
        'src/okto_nexus/adapters/outbound/sqlite/home.py',
        'tests/home_states/test_projection_batch.py', 'pyproject.toml', 'uv.lock',
        'vendor/ci/manifest.json'}
    assert expected and required_inputs.issubset(expected), 'Missing required frozen source/test/lock inputs'
    actual=builder.pins()
    changed=sorted(name for name in expected.keys()|actual.keys() if expected.get(name)!=actual.get(name))
    assert not changed, ('Frozen product/test/build inputs changed',changed)
    static=REPO/'src/okto_nexus/adapters/inbound/http/static'
    assert 'index.html' in frozen['assets']
    for name,pin in frozen['assets'].items():
        path=static/name
        assert path.resolve().is_relative_to(static.resolve()), name
        assert builder.sha(path)==pin, name
    wheel=package/'artifacts/okto_nexus-0.3.7-py3-none-any.whl'
    assert ready['ready'] is True and hashlib.sha256(wheel.read_bytes()).hexdigest()==ready['wheel_sha256']
    assert Path(ready['wheel']).resolve()==wheel.resolve()
    assert build['artifacts'][wheel.name]==ready['wheel_sha256']
    assert ready['version']=='0.3.7' and ready['prefix_frozen'] is True
    prefix=package/'venv'
    assert Path(ready['python']).resolve()==(prefix/'Scripts/python.exe').resolve()
    audit=json.loads((package/'installed-audit.json').read_text())
    assert audit['versions']=={'okto-nexus':'0.3.7','okto-nexus-connector-core':'0.0.14','okto-nexus-connector':'0.0.13'}
    assert all(value['equal_installed_wheel'] for value in audit['modules'].values())
    assert audit['modules']['okto_nexus']['wheel_sha256']==ready['wheel_sha256']
    assert audit['modules']['okto_nexus']['equal_checkout_source'] is True
    for name,pin in frozen['assets'].items():
        assert audit['assets']['okto_nexus/adapters/inbound/http/static/'+name]==pin, name
    # Only this fixture lives outside tests/. Its imports/dynamic loads resolve
    # to stdlib, installed packages, or the already-copied tests/execution_r4.
    helper_inputs={}
    for name in ('NEXUS_UI_R1/execution/fixtures.py',):
        source=REPO/name
        assert not source.is_symlink() and source.resolve().is_relative_to(REPO.resolve()), name
        blob=subprocess.run(['rtk','proxy','git','cat-file','blob',frozen['source_commit']+':'+name],
            cwd=REPO,input=b'',stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=15)
        assert blob.returncode==0, (name,blob.returncode)
        data=source.read_bytes()
        assert data==blob.stdout, ('Helper differs from frozen candidate blob',name)
        helper_inputs[name]=dict(data=data,sha256=hashlib.sha256(data).hexdigest())
    assert not (HERE/'allocation.json').exists(), 'Preserve prior supplemental cuts.'
    root=Path(tempfile.mkdtemp(prefix='nexus-hst-supplement-'))
    (HERE/'allocation.json').write_text(json.dumps(dict(root=str(root)),indent=2)+'\n',encoding='utf-8')
    (root/'TESTS_READY.json').write_text(json.dumps(supplement,indent=2)+'\n',encoding='utf-8')
    for name in ['tree','cwd','tmp','reports','guard']:(root/name).mkdir()
    tree=root/'tree'
    shutil.copytree(REPO/'tests',tree/'tests',ignore=shutil.ignore_patterns('__pycache__','*.pyc','*.pyo'))
    helper_before={}
    for name,value in helper_inputs.items():
        copied_helper=tree/name
        assert copied_helper.resolve().is_relative_to(tree.resolve()), name
        copied_helper.parent.mkdir(parents=True,exist_ok=True)
        copied_helper.write_bytes(value['data'])
        assert copied_helper.read_bytes()==value['data'], name
        helper_before[name]=dict(source_commit=frozen['source_commit'],source_sha256=value['sha256'],
            copied_sha256=hashlib.sha256(copied_helper.read_bytes()).hexdigest())
    (root/'copied-helpers-before.json').write_text(json.dumps(helper_before,indent=2)+'\n',encoding='utf-8')
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
        assert len(result)==ready['payload_files'], (len(result),ready['payload_files'])
        return result
    before=payload()
    (root/'payload-before.json').write_text(json.dumps(before,indent=2)+'\n')
    guard='OUTPUT='+repr(str(root/'reports'))+'\nEXPECTED_PREFIX='+repr(str(prefix))+'\n'+GUARD
    (root/'guard/hst_origin_guard.py').write_text(guard,encoding='utf-8')
    ini=root/'pytest.ini'
    markers=tomllib.loads((REPO/'pyproject.toml').read_text(encoding='utf-8'))['tool']['pytest']['ini_options'].get('markers',[])
    ini.write_text('[pytest]\nasyncio_mode=auto\nasyncio_default_fixture_loop_scope=function\nmarkers=\n'+''.join('    '+m+'\n' for m in markers))
    selected_arguments=[str(p)+suffix for p in selected for suffix in sorted(selectors[p])]
    pytest_args=['-p','hst_origin_guard','-c',str(ini),'--rootdir='+str(tree),'--confcutdir='+str(tree),*selected_arguments,'-v','--tb=short','-o','faulthandler_timeout=0','--junitxml='+str(root/'reports/tests.xml')]
    helper_paths=[str(tree),str(root/'tree/tests'),*[str(p) for p in sorted((root/'tree/tests').rglob('*')) if p.is_dir() and any(p.glob('*.py'))]]
    code='import sys;sys.path[:0]='+repr([str(root/'guard'),*helper_paths])+';import pytest;raise SystemExit(pytest.main('+repr(pytest_args)+'))'
    argv=[str(prefix/'Scripts/python.exe'),'-I','-B','-X','utf8','-c',code]
    env=builder.environment(root)
    env.update(PATH=';'.join([str(prefix/'Scripts'),'C:/Python313','C:/Windows/System32','C:/Windows','C:/Program Files/Git/cmd']),GIT_CONFIG_GLOBAL=os.devnull,GIT_CONFIG_SYSTEM=os.devnull,GIT_CONFIG_NOSYSTEM='1')
    env['QC_DERIVATIVE_OUTPUT']=str(root/'reports')
    for name in ['CODEX_HOME','CLAUDE_CONFIG_DIR']:
        directory=root/name.lower();env[name]=str(directory)
        assert not directory.exists(), 'Provider-home precondition must remain nonexistent.'
    record=dict(started_at=datetime.now(timezone.utc).isoformat(),root=str(root),selected=[str(p.relative_to(tree)) for p in selected],argv=argv,cwd=str(root/'cwd'),helper_paths=helper_paths,stdin='closed PIPE; no NUL console reopening',timeout=args.timeout,signals=[],base_build_source_pin_count=len(build['source_pins']),additional_test_pins=supplement['additions'],guarded_source_test_pin_count=len(expected),runtime_source_commit=frozen['source_commit'],test_closure_scope='Post-build supplement; no application artifact rebuilt or mutated')
    print(json.dumps(dict(status='START',root=str(root),selected=record['selected'])),flush=True)
    known={}
    forced=False
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
                process.send_signal(signal.CTRL_BREAK_EVENT)
                record['signals'].append(dict(kind='CTRL_BREAK_EVENT',pid=process.pid,scope='owned new process group; allows fixture canonical teardown'))
            if interrupted is not None and time.monotonic()-interrupted>30:
                # Every target was observed as a descendant of this exact launched process.
                # Recheck birth and image before containment; preserve all state on timeout.
                for info in reversed(list(known.values())):
                    try:
                        owned=psutil.Process(info['pid'])
                        if owned.create_time()!=info['birth'] or owned.exe()!=info['exe']:
                            continue
                        owned.kill()
                        record['signals'].append(dict(kind='OWNED_TIMEOUT_KILL',**info))
                        forced=True
                    except psutil.NoSuchProcess:
                        pass
                break
            time.sleep(.25)
        record['exit_code']=process.wait(timeout=15)
    remaining=[]
    for info in known.values():
        try:
            owned=psutil.Process(info['pid'])
            if owned.create_time()==info['birth'] and owned.exe()==info['exe']:
                remaining.append(info)
        except psutil.NoSuchProcess:
            pass
    record.update(timed_out=interrupted is not None,forced=forced,remaining_known_processes=remaining,
        observation_limit='250ms descendant polling does not enumerate every short-lived child; no claim that it does.')
    helper_after={}
    for name,value in helper_inputs.items():
        source=REPO/name
        copied_helper=tree/name
        assert source.resolve().is_relative_to(REPO.resolve()) and copied_helper.resolve().is_relative_to(tree.resolve()), name
        helper_after[name]=dict(source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
            copied_sha256=hashlib.sha256(copied_helper.read_bytes()).hexdigest())
    helper_drift=[name for name,value in helper_after.items()
        if value['source_sha256']!=helper_inputs[name]['sha256'] or value['copied_sha256']!=helper_inputs[name]['sha256']]
    (root/'copied-helpers-after.json').write_text(json.dumps(helper_after,indent=2)+'\n',encoding='utf-8')
    record['helper_drift']=helper_drift
    after=payload()
    source_after=builder.pins()
    assert not (tree/'src').exists(), 'Owned test namespace must not contain application src'
    (root/'source-after.json').write_text(json.dumps(source_after,indent=2)+'\n',encoding='utf-8')
    record.update(ended_at=datetime.now(timezone.utc).isoformat(),payload_files=len(after),payload_drift=[p for p in before if before[p]!=after[p]],source_drift=[p for p in sources.keys()|source_after.keys() if sources.get(p)!=source_after.get(p)],known_processes=list(known.values()))
    (root/'payload-after.json').write_text(json.dumps(after,indent=2)+'\n')
    (root/'result.json').write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps(record),flush=True)
    raise SystemExit(record['exit_code'] or bool(record['payload_drift'] or record['source_drift'] or helper_drift or interrupted is not None or remaining))

if __name__=='__main__':main()
