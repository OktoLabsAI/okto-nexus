"""Offline materialization plus authorized read-only power/own-logon probes."""
from pathlib import Path
from datetime import datetime,timezone
import ctypes
import hashlib
import importlib.util
import json
import subprocess
import sys
HERE=Path(__file__).resolve().parent
T=Path('C:/Users/jpamb/AppData/Local/Temp/r3-session-current-history-w6d7vl5_')
E=Path('C:/Users/jpamb/AppData/Local/Temp/r3-svc-session-events-plan-z5l005u4')
Q=Path('C:/Users/jpamb/AppData/Local/Temp/r3-status-fixed-campaign-package-ddwnb5vx')
def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def pin(path):return {'path':str(path),'sha256':digest(path)}
def save(name,value):
    with (HERE/name).open('x',encoding='utf-8',newline='\n') as f:json.dump(value,f,indent=2,sort_keys=True);f.write('\n')
assert Path(sys.prefix).resolve()==(Q/'venv').resolve()
assert digest(E/'event_native.py')=='2e81ec2b62b984ce3337ad7ce13b250a8eaee534376331cb6de97eeacbc28c12'
assert digest(E/'event_observer.py')=='23b506177335e168c087dffce446d99bf024c49a9742ea0a43807459b96667ab'
spec=importlib.util.spec_from_file_location('event_native',E/'event_native.py');native=importlib.util.module_from_spec(spec);spec.loader.exec_module(native)
own=native.own_session_facts()
power=[]
for label,args in [('available',['/a']),('wake-policy',['/query','SCHEME_CURRENT','SUB_SLEEP','RTCWAKE'])]:
    run=subprocess.run([r'C:\Windows\System32\powercfg.exe',*args],capture_output=True,timeout=15)
    assert run.returncode==0
    name='powercfg-'+label+'.txt';(HERE/name).write_bytes(run.stdout)
    power.append({'label':label,'argv':args,'exit_code':0,'output':pin(HERE/name)})
class Power(ctypes.Structure):
    _fields_=[('ACLineStatus',ctypes.c_ubyte),('BatteryFlag',ctypes.c_ubyte),('BatteryLifePercent',ctypes.c_ubyte),
              ('SystemStatusFlag',ctypes.c_ubyte),('BatteryLifeTime',ctypes.c_ulong),('BatteryFullLifeTime',ctypes.c_ulong)]
status=Power();ok=ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(status))
save('capabilities.json',{'observed_utc':datetime.now(timezone.utc).isoformat(),'own_logon':own,'powercfg':power,
    'ac_line_status':status.ACLineStatus if ok else None,'ac_meaning':{'0':'offline','1':'online','255':'unknown'},
    'observed_available':['S0_LOW_POWER_IDLE_NETWORK_CONNECTED','HIBERNATE','FAST_STARTUP'],
    'observed_unavailable':['S1','S2','S3','HYBRID_SLEEP'],'wake_policy':{'AC':1,'DC':0},
    'automatic_wake_guaranteed':False,'manual_wake_fallback_required':True,'policy_changes':0,
    'os_events':0,'scheduled_task_publications':0,'service_controls':0,'provider_calls':0})
plan=json.loads((T/'plan.json').read_bytes())
for key in ('manual_os_actions_only','preparation_facts','before_requires'):plan.pop(key,None)
plan.update(status='OFFLINE_UNSELECTED_AUTOMATION_SUPPLEMENT',root=str(HERE),python=str(Q/'venv/Scripts/python.exe'),
    pythonw=str(Q/'venv/Scripts/pythonw.exe'),python_prefix=str(Q/'venv'),selected_event=None,reviewed_for_execution=False,
    events=['01-suspend-resume','02-sign-out-logon','04-restart-logon'],native_source=str(E/'event_native.py'),
    observer_source=str(E/'event_observer.py'),history_source=str(T/'history.py'),
    ancestor_manual_plan=pin(T/'plan.json'),manual_marker_not_reused=True,os_actions_implemented=False,
    automatic_next_event=False,login_requires_user=True,automatic_wake_selected=False,
    service_controls_implemented=False,event_command_templates_only=True,
    prior_failures_preserved=True,physical_exit_not_inferred_from_absence=True)
plan['task_digests']={'nexus':'b340b00c0def0503a472333948930ace8877e4379bf51946d2f3c96f95a0e235',
                     'connector':'c12aae3497ceb76336f29d3e9f2211733fea86d7ffb8da05568df5f175ae8df3'}
plan['python_images']={str(p):digest(p) for p in [Path('C:/Python313/python.exe'),Path('C:/Python313/pythonw.exe'),Q/'venv/Scripts/python.exe',Q/'venv/Scripts/pythonw.exe']}
plan['read_only_dependencies']=[pin(p) for p in [E/'event_native.py',E/'event_observer.py',T/'history.py',Q/'installation.json',
    HERE/'automation_contract.py',HERE/'collect.py',HERE/'select_event.py']]
save('plan-template.json',plan)
print(json.dumps({'status':'PREPARED_UNSELECTED','power_queries':2,'own_logon_only':True,'plan_sha256':digest(HERE/'plan-template.json')}))
