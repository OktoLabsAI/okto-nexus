"""Gated browser-only native dialog diagnostic. Never starts or imports Nexus."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

import psutil

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[3]
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
def write(path,value):
    with path.open('x',encoding='utf-8')as stream:stream.write(json.dumps(value,indent=2)+'\n')
def check(gate_path):
    manifest_path=HERE/'prepared.json';manifest=json.loads(manifest_path.read_text());gate=json.loads(gate_path.read_text())
    assert gate['approved']is True and gate['scope']=='NATIVE_DIALOG_FOCUS_BROWSER_ONLY'and gate['start_nexus']is False
    assert gate['deadline_seconds']==180 and gate['allow_own_containment']is True
    assert re.fullmatch(r'hst-native-zoom-r9-[a-z0-9-]{1,60}',gate['cut_id'])
    assert gate['manifest_sha256']==sha(manifest_path)
    for path,digest in manifest['input_pins'].items():assert sha(REPO/path)==digest,'Prepared input drift: '+path
    ready_path=REPO/manifest['ready'];assert sha(ready_path)==manifest['ready_sha256']
    ready=json.loads(ready_path.read_text());assert ready['ready']and ready['prefix_frozen']and ready['source_commit']==manifest['source_commit']and ready['wheel_sha256']==manifest['wheel_sha256']
    assert sha(ready['wheel'])==ready['wheel_sha256']
    payload_path=ready_path.parent/'evidence/payload-manifest.json';assert sha(payload_path)==manifest['payload_manifest_sha256']
    payload=json.loads(payload_path.read_text());site=Path(ready['python']).parent.parent/'Lib/site-packages'
    assert sum(map(len,payload.values()))==ready['payload_files']==1031
    assert all(sha(site/name)==digest for group in payload.values()for name,digest in group.items())
    pins_path=ready_path.parent/'evidence/source-pins-after.json';assert sha(pins_path)==manifest['source_pin_manifest_sha256']
    source=json.loads(pins_path.read_text());assert len(source)==1829 and all(sha(REPO/name)==digest for name,digest in source.items())
    tooling=manifest['tooling'];assert sha(tooling['node'])==tooling['node_sha256']and sha(tooling['chrome'])==tooling['chrome_sha256']
    modules=Path(tooling['node_modules']);actual={path.relative_to(modules).as_posix():sha(path)for name in ['@playwright/cli','playwright','playwright-core']for path in(modules/name).rglob('*')if path.is_file()}
    assert actual==tooling['cli_payload_pins']
    assert json.loads((modules/'@playwright/cli/package.json').read_text())['version']=='0.1.24'
    runtime=manifest['probe_runtime']
    prefix=Path(ready['python']).parent.parent
    assert sha(prefix/'pyvenv.cfg')==runtime['venv_config_sha256'],'Frozen venv metadata drift'
    assert sha(ready['python'])==runtime['venv_python_sha256'],'Frozen venv launcher drift'
    assert sha(runtime['base_executable'])==runtime['base_executable_sha256'],'Expected base interpreter drift'
    return dict(manifest_sha256=sha(manifest_path),gate_sha256=sha(gate_path),source_commit=ready['source_commit'],wheel_sha256=ready['wheel_sha256'],payload_files=1031,source_files=1829,cli_files=len(actual)),manifest,gate,ready
def main():
    p=argparse.ArgumentParser();p.add_argument('--gate',type=Path,required=True);a=p.parse_args()
    before,manifest,gate,ready=check(a.gate)  # All guards BEFORE allocation/process.
    attempt=HERE/('attempt-'+gate['cut_id']+'.json');write(attempt,before)
    total_deadline=time.monotonic()+180;action_deadline=total_deadline-30
    browser=REPO/'NEXUS_HOME_ESTADOS_R1/execution/browser-hst';security=REPO/'NEXUS_HOME_ESTADOS_R1/execution/remaining-qualification-r7-next/security-r9-batch'
    prepared=subprocess.run([sys.executable,'-B',str(browser/'prepare_runtime.py'),'--package-ready',str((REPO/manifest['ready']).resolve()),'--expected-source',ready['source_commit'],'--mode','baseline','--browser-window-open'],input=b'',capture_output=True,timeout=20,check=True)
    root=Path(json.loads(prepared.stdout)['root']).resolve();print(json.dumps(dict(event='ALLOCATED',root=str(root))),flush=True)
    # Allocation copies fixture source but NEVER starts it. Only this static probe runs.
    shutil.copyfile(HERE/'probe_server_v2.py',root/'zoom-probe.py');shutil.copyfile(HERE/'playwright-cli.json',root/'playwright-cli.json')
    manager=load('zoom_commands',security/'run.py');driver=load('zoom_browser_driver',security/'browser_driver.py');lifecycle=load('zoom_probe_environment',browser/'containment.py')
    commands=manager.Commands(root,driver.environment(root),action_deadline);tooling=manifest['tooling'];rtk=shutil.which('rtk');assert rtk
    opened=False;probe=None;probe_log=None;result=None;failure=None;cleanup_errors=[];port=None;after=None;argv_proof=None
    def cli(name,*arguments,cleanup=False):
        return commands.run(name,[rtk,'proxy',tooling['node'],tooling['entry'],'--session='+gate['cut_id'],*arguments],timeout=10 if cleanup else 75,cleanup=cleanup)
    try:
        opened=True  # Even a partial launch must receive one owned close attempt.
        cli('launch-browser','open','about:blank','--browser=chrome','--profile='+str(root/'browser-profile'),'--config='+str(root/'playwright-cli.json'))
        commands.sample();argv_proof=driver.capture(root,commands.known,tooling);write(root/'chrome-argv.private.json',argv_proof)
        probe_log=(root/'probe.private.log').open('wb')
        probe=subprocess.Popen([ready['python'],'-I','-B',str(root/'zoom-probe.py'),'--root',str(root),'--window','ROOT_NATIVE_DIALOG_FOCUS'],cwd=root/'cwd',env=lifecycle.environment(root),stdin=subprocess.PIPE,stdout=probe_log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
        probe.stdin.close();commands.sample(probe.pid)
        end=min(action_deadline,time.monotonic()+15)
        while not(root/'control/zoom-probe-ready.json').exists():
            assert probe.poll()is None and time.monotonic()<end,'Static calibration server did not become ready'
            commands.sample(probe.pid);time.sleep(.1)
        probe_ready_path=root/'control/zoom-probe-ready.json'
        assert not probe_ready_path.is_symlink()and probe_ready_path.resolve().is_relative_to((root/'control').resolve())
        probe_ready=json.loads(probe_ready_path.read_text());port=int(probe_ready['origin'].rsplit(':',1)[1])
        commands.sample(probe.pid)
        actual_pid=probe_ready['pid'];assert type(actual_pid)is int and actual_pid>0,'Invalid worker PID'
        actual_record=commands.known.get(actual_pid);assert actual_record and commands.alive(actual_record),'Worker birth was not observed alive'
        parent_record=commands.known.get(probe.pid);assert parent_record and commands.alive(parent_record),'Popen launcher birth is not current'
        actual=psutil.Process(actual_pid);runtime=manifest['probe_runtime']
        assert Path(actual.exe()).resolve()==Path(runtime['base_executable']).resolve(),'Unexpected effective interpreter executable'
        assert Path(parent_record['exe']).resolve()==Path(ready['python']).resolve(),'Unexpected venv launcher executable'
        assert Path(probe_ready['prefix']).resolve()==Path(ready['python']).parent.parent.resolve(),'Unexpected interpreter prefix'
        assert Path(probe_ready['executable']).resolve()==Path(ready['python']).resolve(),'Unexpected sys.executable'
        assert Path(probe_ready['base_executable']).resolve()==Path(runtime['base_executable']).resolve(),'Unexpected base interpreter declaration'
        assert Path(probe_ready['root']).resolve()==root,'Worker root mismatch'
        worker=(root/'zoom-probe.py').resolve()
        assert Path(probe_ready['worker']).resolve()==worker and worker.is_relative_to(root),'Worker path mismatch'
        assert probe_ready['worker_sha256']==sha(worker)==sha(HERE/'probe_server_v2.py'),'Worker bytes mismatch'
        ancestry=[];cursor=actual;found=False
        for unused in range(16):
            record=commands.known.get(cursor.pid)
            assert record and commands.alive(record),'Unobserved/reused process in worker ancestry'
            ancestry.append(record)
            if cursor.pid==probe.pid:found=True;break
            cursor=cursor.parent()
            if cursor is None:break
        assert found,'Worker is not the actual Popen process or its observed descendant'
        write(root/'probe-process-proof.json',dict(popen_pid=probe.pid,actual_pid=actual_pid,ancestry=ancestry,worker_sha256=sha(worker),prefix=probe_ready['prefix'],executable=probe_ready['executable'],base_executable=probe_ready['base_executable'],root=str(root),same_process=actual_pid==probe.pid))
        cfg=dict(window='ROOT_NATIVE_DIALOG_FOCUS',probeOrigin=probe_ready['origin'],outputPrefix=str(root/'native-zoom'))
        source=(HERE/'diagnostic.js').read_text();assert source.count('__CONFIG__')==1
        (root/'native-zoom.js').write_text(source.replace('__CONFIG__',json.dumps(cfg)),encoding='utf-8')
        cli('before-diagnostic','snapshot')
        result=manager.cli_result(cli('native-guard','run-code','--filename='+str(root/'native-zoom.js')));write(root/'native-guard-result.private.json',result)
        assert result['status']=='DIAGNOSTIC_COMPLETED_NATIVE_DIALOG','Native dialog diagnostic incomplete; no rerun/fallback/Nexus startup'
    except BaseException as error:
        failure=dict(type=type(error).__name__,message=str(error));write(root/'first-failure.private.json',failure)
    finally:
        # Normal close/stop FIRST. No retry and no next-stage application branch.
        if opened:
            try:cli('cleanup-browser','close',cleanup=True)
            except BaseException as error:cleanup_errors.append(dict(stage='CLI close',type=type(error).__name__))
        (root/'control/zoom-probe-stop').touch()
        end=min(total_deadline,time.monotonic()+15)
        while probe and probe.poll()is None and time.monotonic()<end:commands.sample(probe.pid);time.sleep(.1)
        commands.sample();remaining=commands.remaining();containment=commands.contain()if remaining else dict(forced_births=[],remaining=[])
        if containment['forced_births']or containment['remaining']:cleanup_errors.append(dict(stage='owned containment',classification='DIAGNOSTIC_FAIL'))
        if probe_log:probe_log.close()
        listeners=[dict(pid=item.pid,port=item.laddr.port)for item in psutil.net_connections(kind='tcp')if port and item.status=='LISTEN'and item.laddr.port==port]
        try:
            after=check(a.gate)[0];assert before==after
            assert sha(root/'zoom-probe.py')==sha(HERE/'probe_server_v2.py')and sha(root/'playwright-cli.json')==sha(HERE/'playwright-cli.json')
        except BaseException as error:cleanup_errors.append(dict(stage='final pin guard',type=type(error).__name__))
        probe_final_path=root/'control/zoom-probe-final.json';probe_final=json.loads(probe_final_path.read_text())if probe_final_path.exists()else None
        if probe and(probe.poll()!=0 or not probe_final or probe_final['server_thread_alive']):cleanup_errors.append(dict(stage='probe normal settlement',exit_code=probe.poll()))
        if listeners:cleanup_errors.append(dict(stage='listener remains',listeners=listeners))
        final=dict(scope='NATIVE_DIALOG_FOCUS_BROWSER_ONLY',cut_id=gate['cut_id'],root=str(root),result=result,first_failure=failure,cleanup_errors=cleanup_errors,before=before,after=after,commands=commands.commands,known_births=list(commands.known.values()),containment=containment,listeners=listeners,probe_exit_code=probe.poll()if probe else None,probe_final=probe_final,browser_argv=argv_proof,deadline_seconds=180,nexus_processes_started=0,provider_invocations=0,sampling_limit='Observed process ancestry and exact own-root/birth scan; not every short-lived child')
        write(root/'native-zoom-run.private.json',final)
        print(json.dumps(dict(event='FINISHED',root=str(root),browser_status=result.get('status')if result else None,failure=failure,cleanup_errors=cleanup_errors,remaining_births=len(containment['remaining']),nexus_started=False)),flush=True)
    return int(bool(failure or cleanup_errors))
if __name__=='__main__':raise SystemExit(main())
