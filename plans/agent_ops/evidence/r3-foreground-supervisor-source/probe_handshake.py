"""Three finite normal Python processes; no task, server, DB or model call."""
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time

sys.path[:0] = ['D:/Projetos/Techridy/okto_labs_okto_nexus/src',
                'D:/Projetos/Techridy/okto-nexus-connector-core/src']
from okto_nexus.adapters.outbound.service_manager import supervision as s
from okto_nexus.adapters.outbound.service_manager.context import atomic_json, read_json
from okto_nexus.adapters.outbound.service_manager.local import launch_exclusion
from okto_nexus.adapters.inbound.cli.service_supervisor import _await_runtime

root = Path(__file__).resolve().parent
scope = root/'benign-handshake'
scope.mkdir(exist_ok=False)
pythonw = Path('C:/Users/jpamb/AppData/Local/Temp/r3-native-t19-t20-39ycaumc/venv/Scripts/pythonw.exe')
results = []
previous = None
for mode in ('normal', 'stop-during-handshake', 'previous-parent-exited'):
    home = scope/mode
    home.mkdir()
    meta = {'instance_id':'svc_'+'a'*64,'token':'b'*32,'cycle_id':secrets.token_hex(16),
            'nonce':secrets.token_hex(16),'mode':mode}
    atomic_json(home/'probe.json',meta)
    class Installation:
        instance_id = meta['instance_id']
        def receipt(self): return {'token':meta['token']}
        def control(self, receipt): return read_json(home/'service-control.json')
    installation = Installation()
    parent = {'pid':os.getpid(),'birth':s.own_birth()} if previous is None or mode!='previous-parent-exited' else previous
    record = {'revision':1,'token':meta['token'],'instance_id':meta['instance_id'],
              'cycle_id':meta['cycle_id'],'attempt_nonce':meta['nonce'],'attempts_started':1,
              'phase':'running','next_retry_monotonic':None,'last_exit_code':None,
              'parent':parent,'launcher':None,'child':None,'child_acknowledged':False}
    atomic_json(home/'service-control.json',{'token':meta['token'],'desired':'running','cycle_id':meta['cycle_id']})
    runtime = None
    launcher = None
    try:
        with launch_exclusion(home,home/'never-created.db'):
            atomic_json(home/'service-supervisor.json',record)
            launcher = subprocess.Popen([str(pythonw),'-I','-B','-X','utf8',str(root/'handshake_child.py'),str(home)],
                stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,close_fds=True)
            record['launcher'] = {'pid':launcher.pid,'birth':s.handle_birth(launcher._handle),'physical_exit':False}
            atomic_json(home/'service-supervisor.json',record)
        if mode == 'previous-parent-exited':
            deadline = time.monotonic()+30
            while not (home/'probe-runtime-identity.json').exists() and time.monotonic()<deadline:
                time.sleep(.02)
            identity = read_json(home/'probe-runtime-identity.json')
            runtime = s.retain_runtime(launcher,record['launcher']['birth'],identity)
        else:
            runtime, handshake = _await_runtime(home,home/'never-created.db',installation,meta['token'],record,launcher)
            assert not (home/'bootstrap-marker.json').exists(), 'Bootstrap preceded parent ACK'
            with launch_exclusion(home,home/'never-created.db'):
                if mode=='stop-during-handshake':
                    atomic_json(home/'service-control.json',{'token':meta['token'],'desired':'draining','cycle_id':meta['cycle_id']})
                record['child'] = {'pid':runtime.pid,'birth':runtime.birth,'physical_exit':False}
                record['child_acknowledged'] = True
                atomic_json(home/'service-supervisor.json',record)
        launcher_code = launcher.wait(timeout=90)
        runtime_code = runtime.wait()
        result = {'mode':mode,'launcher':record['launcher'],
                  'runtime':{'pid':runtime.pid,'birth':runtime.birth},
                  'launcher_exit_code':launcher_code,'runtime_exit_code':runtime_code,
                  'both_physical_exits_confirmed':True,'bootstrap_marker':(home/'bootstrap-marker.json').exists(),
                  'child_result':read_json(home/'child-result.json')}
        assert result['bootstrap_marker'] == (mode=='normal')
        assert launcher_code == runtime_code == (2 if mode=='previous-parent-exited' else 0)
        previous = {'pid':launcher.pid,'birth':record['launcher']['birth']}
        results.append(result)
    finally:
        if launcher is not None: launcher.wait()
        if runtime is not None:
            runtime.wait()
            runtime.close()
value = {'status':'PASS','cases':results,'service_calls':0,'tasks_created':0,'model_turns':0,
         'force_used':False,'scope':'Source handshake and Windows redirector ownership only; no runtime bootstrap occurred (marker is a probe file).'}
with (root/'benign-handshake-result.json').open('x',encoding='utf-8') as out: json.dump(value,out,indent=2)
print(json.dumps(value))
