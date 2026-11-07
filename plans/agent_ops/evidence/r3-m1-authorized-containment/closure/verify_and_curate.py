from pathlib import Path
import ctypes,hashlib,json,shutil,socket,sqlite3,sys,time
from ctypes import wintypes
HERE=Path(__file__).parent;PUBLIC=HERE/'public'
TEMP=Path('C:/Users/jpamb/AppData/Local/Temp')
sys.path.insert(0,str(TEMP))
from m1_real_lifecycle import P,C,ROOT
from okto_nexus.adapters.outbound.service_manager.installation import ServerInstallation
from okto_nexus_connector.platform.user_service import UserService
assert json.loads((PUBLIC/'exit-observation.json').read_text())['confirmed_exit']
uninstall=json.loads((ROOT/'public/lifecycle-nexus-uninstall.json').read_text())
assert uninstall['returncode']==0
home=Path(P['paths']['server_home'])
task=ServerInstallation(home,home/'nexus.db')
assert task.name==P['topology']['task_names']['nexus'] and task.tasks.read(task.name) is None
connector=UserService(Path(P['paths']['connector_state']))
assert connector.name==P['topology']['task_names']['connector'] and connector.tasks.read(connector.name) is None
kernel=ctypes.WinDLL('kernel32',use_last_error=True)
kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];kernel.OpenProcess.restype=wintypes.HANDLE
kernel.CloseHandle.argtypes=[wintypes.HANDLE]
handle=kernel.OpenProcess(0x1000,False,45144)
if handle:
    kernel.CloseHandle(handle)
    raise AssertionError('Original PID is still addressable; do not declare absent')
assert ctypes.get_last_error()==87
with socket.socket() as probe:
    probe.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
    probe.bind(('127.0.0.1',64507))
state=json.loads((ROOT/'private/controller.json').read_text())
assert len(state['requests'])==2 and state['faults']==['CAMPAIGN_RUNNER_EXCEPTION']
c=state['collector']['state']
known=state['requests']['m1-local-setup']['monitor']['high_water']+sum(t['high_water']-t['baseline'] for t in c['threads'].values())
assert known==45843
journal=home/'core-runtime/session-ef244ce98fccbe3be1dc54013ba7dc75abcde017ba84fcc06c29438903cefd99.db'
with sqlite3.connect(journal.as_uri()+'?mode=ro',uri=True) as db:
    db.execute('PRAGMA query_only=ON')
    rows=db.execute('SELECT stream_epoch,next_sequence,acked_sequence,compacted_sequence FROM event_streams').fetchall()
    claims=db.execute('SELECT server_id,executor_id,session_id,operation_id,reconciliation_pending,release_id,release_digest FROM session_claims').fetchall()
assert len(rows)==1 and rows[0][1:]==(35,34,0)
snapshot={'recorded_at':time.time(),'original_pid':45144,'original_pid_absent':True,
    'nexus_task_absent':True,'connector_task_absent':True,'port64507_available':True,
    'admissions':2,'known_observed_token_minimum':known,'final_billed_usage':False,
    'controller_faults_preserved':state['faults'],'additional_provider_admissions':0,
    'post_containment_event_streams':[{'stream_epoch':r[0],'next_sequence':r[1],'acked_sequence':r[2],'compacted_sequence':r[3]} for r in rows],
    'post_containment_claims':[dict(zip(('server_id','executor_id','session_id','operation_id','reconciliation_pending','release_id','release_digest'),r)) for r in claims],
    'history_preserved':'Earlier UNKNOWN drain receipts and partial milestone ec8f2a5d remain immutable; successful containment does not promote cooperative drain or M1 acceptance.'}
(PUBLIC/'final-verification.json').write_text(json.dumps(snapshot,indent=2))
for name in ('lifecycle-nexus-uninstall.json','process-nexus-uninstall.json'):
    shutil.copyfile(ROOT/'public'/name,PUBLIC/name)
for name in ('execute_force.py','verify_and_curate.py'):
    shutil.copyfile(HERE/name,PUBLIC/name)
shutil.copyfile(ROOT/'public/force-recovery-proposal.json',PUBLIC/'approved-force-proposal.json')
summary={'status':'AUTHORIZED_CONTAINMENT_COMPLETED_AND_OWNED_TASK_REMOVED','force_executions':1,
    'force_cli_exit':0,'uninstall_executions':1,'uninstall_cli_exit':0,
    'original_pid_absent':True,'owned_task_absent':True,'connector_task_never_installed':True,
    'port64507_available':True,'historical_server_packages_unchanged':True,'hotpatch':False,
    'additional_provider_admissions':0,'total_admissions':2,'known_observed_token_minimum':45843,
    'permanent_controller_fault_preserved':True,'cooperative_drain_qualified_by_this_force':False,'m1_accepted':False,
    'prior_partial_milestone':'ec8f2a5d','separate_core_fix_not_installed_live':'830f7ce',
    'scope':'One user-authorized generation-CAS force with task/PID/birth/digest/package/deadline verification; uninstall only after confirmed exit.'}
(PUBLIC/'summary.json').write_text(json.dumps(summary,indent=2))
(PUBLIC/'README.md').write_text('''# M1 authorized containment closure

The user explicitly authorized the exact generation-bound force proposal.
Preflight reconfirmed the original task digest, PID45144/birth, generation,
expired drain deadline, force availability and all 981 historical package files.
Authorization and the single invocation reservation were persisted before
dispatch. The original pinned CLI returned0; read-only observation confirmed
the original PID absent and service stopped. Only then did the already proposed
uninstall run, returning0. Final checks found both M1 task names absent and
port64507 available. Connector was never installed.

No provider admission, process kill fallback, force replay, Core hotpatch,
checkpoint reset or data deletion occurred. Two original admissions and the
45,843-token observed minimum remain; final billing is not asserted. The
controller's permanent fault remains. Stream metadata after containment is
still next35/ACK34/compacted0, matching the observed prefix.

This closure is separate from the immutable partial milestone ec8f2a5d.
Earlier UNKNOWN drain records remain historical facts. Forced containment does
not qualify cooperative draining, complete M1, or authorize another campaign.
The separately tested Core fix was not installed into the live M1 environment.
Public files omit raw subprocess output, credentials, databases and homes.
''',encoding='utf-8')
manifest=[]
for path in sorted(PUBLIC.iterdir()):
    if path.is_file():manifest.append({'path':path.name,'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
(PUBLIC/'manifest.json').write_text(json.dumps({'files':manifest},indent=2)+'\n')
print(json.dumps({'public':str(PUBLIC),'payloads':len(manifest),'manifest_sha256':hashlib.sha256((PUBLIC/'manifest.json').read_bytes()).hexdigest(),'final':snapshot}))
