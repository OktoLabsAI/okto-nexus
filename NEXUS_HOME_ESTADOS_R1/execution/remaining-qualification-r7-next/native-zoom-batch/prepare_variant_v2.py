"""Static PID/locale oracle counterpart. No application/browser/probe execution."""
import ast
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
assert sha(HERE/'prepared-bound.json')=='a42997692daa7030ee34efbd61ca876223abcf2eaa32bcd422e599dd14ca31ce'
old=json.loads((HERE/'prepared-bound.json').read_text());repo=HERE.parents[3]
assert not any((HERE/name).exists()for name in ['native-settings-guard-v2.js','probe_server_v2.py','run_v2.py','curate_v2.py']),'Never overwrite a prepared counterpart'
def original(name):
    path=HERE/name;assert sha(path)==old['input_pins'][str(path.relative_to(repo)).replace('\\','/')];return path.read_text()
guard=original('native-settings-guard.js');needle='/^(Page zoom|Zoom da página)$/i';assert guard.count(needle)==1
(HERE/'native-settings-guard-v2.js').write_text(guard.replace(needle,'/^(Page zoom|Zoom da página):?$/i'),encoding='utf-8')
probe=original('probe_server.py');assert probe.count('import os\n')==1
probe=probe.replace('import os\n','import os\nimport sys\nimport hashlib\n')
needle="ready=dict(pid=os.getpid(),origin=";assert probe.count(needle)==1
probe=probe.replace(needle,"ready=dict(pid=os.getpid(),root=str(root),worker=str(Path(__file__).resolve()),worker_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),prefix=sys.prefix,executable=sys.executable,base_executable=sys._base_executable,origin=")
(HERE/'probe_server_v2.py').write_text(probe,encoding='utf-8');ast.parse(probe)
runner=original('run.py')
runner=runner.replace("HERE/'prepared-bound.json'","HERE/'prepared-bound-v2.json'")
runner=runner.replace("HERE/'probe_server.py'","HERE/'probe_server_v2.py'")
runner=runner.replace("HERE/'native-settings-guard.js'","HERE/'native-settings-guard-v2.js'")
needle="    return dict(manifest_sha256=";assert runner.count(needle)==1
runtime_guard="""    runtime=manifest['probe_runtime']
    prefix=Path(ready['python']).parent.parent
    assert sha(prefix/'pyvenv.cfg')==runtime['venv_config_sha256'],'Frozen venv metadata drift'
    assert sha(ready['python'])==runtime['venv_python_sha256'],'Frozen venv launcher drift'
    assert sha(runtime['base_executable'])==runtime['base_executable_sha256'],'Expected base interpreter drift'
"""
runner=runner.replace(needle,runtime_guard+needle)
needle="probe_ready=json.loads((root/'control/zoom-probe-ready.json').read_text());port=int(probe_ready['origin'].rsplit(':',1)[1]);assert probe_ready['pid']==probe.pid"
assert runner.count(needle)==1
proof="""probe_ready_path=root/'control/zoom-probe-ready.json'
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
        write(root/'probe-process-proof.json',dict(popen_pid=probe.pid,actual_pid=actual_pid,ancestry=ancestry,worker_sha256=sha(worker),prefix=probe_ready['prefix'],executable=probe_ready['executable'],base_executable=probe_ready['base_executable'],root=str(root),same_process=actual_pid==probe.pid))"""
runner=runner.replace(needle,proof);ast.parse(runner)
(HERE/'run_v2.py').write_text(runner,encoding='utf-8')
curator=original('curate.py');needle="names=['native-zoom-run.private.json',";assert curator.count(needle)==1
curator=curator.replace(needle,"names=['probe-process-proof.json','native-zoom-run.private.json',")
(HERE/'curate_v2.py').write_text(curator,encoding='utf-8');ast.parse(curator)
print(json.dumps(dict(status='STATIC_VARIANT_WRITTEN_NOT_EXECUTED',files={name:sha(HERE/name)for name in ['native-settings-guard-v2.js','probe_server_v2.py','run_v2.py','curate_v2.py']}),indent=2))
