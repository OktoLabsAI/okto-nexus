"""One specifically authorized generation-bound force; no provider or replay."""
from pathlib import Path
import ctypes,hashlib,json,os,subprocess,sys,time,zipfile
from ctypes import wintypes
HERE=Path(__file__).parent
PUBLIC=HERE/'public';PRIVATE=HERE/'private'
TEMP=Path('C:/Users/jpamb/AppData/Local/Temp')
sys.path.insert(0,str(TEMP))
from m1_real_lifecycle import P,C,ROOT,env
from okto_nexus.adapters.inbound.cli.service import resolve_local_service
import okto_nexus,okto_nexus_connector,nexus_connector_core
PROPOSAL=ROOT/'public/force-recovery-proposal.json'
EXPECTED_SHA='d9e8b53dbbadcd991e170d801aa5483d875d982ee4a5627656994239b73a8261'
assert hashlib.sha256(PROPOSAL.read_bytes()).hexdigest()==EXPECTED_SHA
proposal=json.loads(PROPOSAL.read_text())
assert Path(sys.prefix).resolve()==Path(P['package_pins']['nexus']['python_path']).parents[1].resolve()
def save(name,value):
    with (PUBLIC/name).open('x',encoding='utf-8') as f:
        json.dump(value,f,indent=2);f.flush();os.fsync(f.fileno())
save('authorization.json',{'user_answer_verbatim':'Autorizar essa parada forçada',
    'relayed_by':'root','recorded_at':time.time(),'proposal_sha256':EXPECTED_SHA,
    'authorized_effect':'One exact force invocation for PID45144/birth134385414258428432/generation188be445d44e96d483336ee424008e56; original uninstall only after confirmed exit.',
    'provider_admissions_authorized_here':0,'prior_partial_milestone':'ec8f2a5d'})
proof={}
for name,module in [('nexus',okto_nexus),('connector',okto_nexus_connector),('core',nexus_connector_core)]:
    pin=P['package_pins'][name];wheel=Path(pin['wheel']);package=Path(module.__file__).resolve().parent
    assert package==Path(pin['installed_import_path']).resolve()
    assert hashlib.sha256(wheel.read_bytes()).hexdigest()==pin['wheel_sha256']
    with zipfile.ZipFile(wheel) as z:
        expected={n.split('/',1)[1]:hashlib.sha256(z.read(n)).hexdigest() for n in z.namelist() if n.startswith(module.__name__+'/') and not n.endswith('/')}
    actual={f.relative_to(package).as_posix():hashlib.sha256(f.read_bytes()).hexdigest() for f in package.rglob('*') if f.is_file() and '__pycache__' not in f.parts and f.suffix not in ('.pyc','.pyo')}
    assert actual==expected
    proof[name]={'wheel_sha256':pin['wheel_sha256'],'payload_files':len(actual),'import_path':str(package)}
save('historical-package-proof.json',proof)
kernel=ctypes.WinDLL('kernel32',use_last_error=True)
kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];kernel.OpenProcess.restype=wintypes.HANDLE
kernel.GetProcessTimes.argtypes=[wintypes.HANDLE,*([ctypes.POINTER(wintypes.FILETIME)]*4)];kernel.GetProcessTimes.restype=wintypes.BOOL
kernel.CloseHandle.argtypes=[wintypes.HANDLE];kernel.CloseHandle.restype=wintypes.BOOL
def process_birth(pid):
    handle=kernel.OpenProcess(0x1000,False,pid)
    if not handle:
        if ctypes.get_last_error()==87:return None
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        stamps=[wintypes.FILETIME() for _ in range(4)]
        if not kernel.GetProcessTimes(handle,*[ctypes.byref(s) for s in stamps]):raise ctypes.WinError(ctypes.get_last_error())
        return (stamps[0].dwHighDateTime<<32)|stamps[0].dwLowDateTime
    finally:kernel.CloseHandle(handle)
service=resolve_local_service(C['service_selection_args'])
before=service.inspect()
birth=process_birth(proposal['pid'])
expected_digest='ebaff7b4de4649e868fce01bddceb44f8c24b1626c4915b0d370d1dd576f8d3f'
task=before['user_service']
assert task['name']==proposal['task_name'] and task['definition_digest']==expected_digest
assert before['effective_configuration']['home']==P['paths']['server_home']
assert before['effective_configuration']['port']==64507
natural=before['state']=='stopped' and birth is None
if not natural:
    assert before['generation']==proposal['generation'] and before['pid']==proposal['pid']
    assert birth==proposal['birth']
    shutdown=before['shutdown']
    assert before['admission']=='closed' and shutdown['force_available'] is True
    assert shutdown['deadline_monotonic']<time.monotonic()
save('preflight.json',{'time':time.time(),'status':before,'birth':birth,'natural_exit_before_force':natural,
                      'task_digest_verified':expected_digest,'proposal_sha256':EXPECTED_SHA})
force_code=None
if not natural:
    save('force-reservation.json',{'state':'RESERVED_BEFORE_DISPATCH','time':time.time(),'argv':proposal['argv'],
                                 'generation':proposal['generation'],'pid':proposal['pid'],'birth':birth,'attempt':1})
    with (PRIVATE/'force.stdout').open('xb') as out,(PRIVATE/'force.stderr').open('xb') as err:
        child=subprocess.Popen(proposal['argv'],cwd=ROOT,env=env(),stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
        save('force-process.json',{'pid':child.pid,'created_at':time.time()})
        force_code=child.wait() # never timeout-kill or replay this invocation
    raw=(PRIVATE/'force.stdout').read_bytes()
    try:receipt=json.loads(raw.decode('utf-8'))
    except UnicodeDecodeError:receipt=json.loads(raw.decode('cp1252'))
    except ValueError:receipt={'unparseable_output':True}
    save('force-receipt.json',{'exit_code':force_code,'receipt':receipt,
        'stdout_sha256':hashlib.sha256(raw).hexdigest(),'stderr_sha256':hashlib.sha256((PRIVATE/'force.stderr').read_bytes()).hexdigest()})
deadline=time.monotonic()+120
while True:
    status=service.inspect();current_birth=process_birth(proposal['pid'])
    if current_birth is not None:assert current_birth==proposal['birth'],'PID identity changed; refuse further effects'
    if status.get('generation') is not None:assert status['generation']==proposal['generation']
    exited=current_birth is None and status['state']=='stopped'
    if exited or time.monotonic()>=deadline:break
    time.sleep(1)
save('exit-observation.json',{'time':time.time(),'original_pid_present':current_birth is not None,
    'observed_birth':current_birth,'status':status,'confirmed_exit':exited,'force_executions':0 if natural else 1})
print(json.dumps({'force_executions':0 if natural else 1,'force_cli_exit':force_code,'confirmed_exit':exited,'state':status['state'],'public':str(PUBLIC)}),flush=True)
if not exited:raise SystemExit(3)
