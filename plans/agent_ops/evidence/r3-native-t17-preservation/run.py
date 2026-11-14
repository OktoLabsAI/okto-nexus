"""SVC-T17 native finite test: registration only, no service start or provider."""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
B = Path('C:/Users/jpamb/AppData/Local/Temp/m1-v12-bundle-bldo9qy7')
PROPOSAL = B / 'draft/m1-codex-campaign-proposal-v12.json'
PROPOSAL_SHA = 'd6b1340956fe5ed83cb16f56dd8af13c16c65341d9d517280ac2f6109d561040'
REPO = Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
PUBLIC = ROOT / 'public'
PRIVATE = ROOT / 'private'

def require(ok, code):
    if not ok:
        raise ValueError(code)

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def save(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as f:
        json.dump(value, f, indent=2)
        f.write('\n')

def secure(path):
    import ntsecuritycon, win32api, win32con, win32security
    require(path.resolve().is_relative_to(ROOT), 'OUTSIDE_TEST_ROOT')
    path.mkdir(exist_ok=True)
    token = win32security.OpenProcessToken(win32api.GetCurrentProcess(), win32con.TOKEN_QUERY)
    try:
        user = win32security.GetTokenInformation(token, win32security.TokenUser)[0]
    finally:
        token.Close()
    system = win32security.CreateWellKnownSid(win32security.WinLocalSystemSid, None)
    acl = win32security.ACL()
    for sid in (user, system):
        acl.AddAccessAllowedAceEx(win32security.ACL_REVISION, 3, ntsecuritycon.FILE_ALL_ACCESS, sid)
    win32security.SetNamedSecurityInfo(str(path), win32security.SE_FILE_OBJECT,
        win32security.DACL_SECURITY_INFORMATION | win32security.PROTECTED_DACL_SECURITY_INFORMATION,
        None, None, acl, None)

def pins():
    require(sha(PROPOSAL) == PROPOSAL_SHA, 'PACKAGE_REFERENCE_CHANGED')
    p = json.loads(PROPOSAL.read_bytes())['package_pins']
    require(Path(sys.executable).resolve() == Path(p['python']).resolve() and sys.flags.isolated, 'RUNTIME_CHANGED')
    for item in p['files']:
        require(sha(item['path']) == item['sha256'], 'INSTALLED_PAYLOAD_CHANGED')
    return {'proposal_sha256': PROPOSAL_SHA, 'verified_files': len(p['files']),
        'python': sys.executable, 'packages': {k:{f:v[f] for f in ('sha256','files','wheel')} for k,v in p['packages'].items()}}

def configure():
    require(ROOT == Path('C:/Users/jpamb/AppData/Local/Temp/r3-native-t17-x8dcs3j3'), 'TEST_ROOT_CHANGED')
    for name in ('private','nexus','connector','project','profile'):
        secure(ROOT / name)
    PUBLIC.mkdir(exist_ok=True)
    for name in ('appdata','localappdata','tmp'):
        (ROOT / 'profile' / name).mkdir(exist_ok=True)
    old = json.loads((REPO/'plans/agent_ops/evidence/r3-native-user-service-execution/campaign/proposal-revision4.json').read_bytes())
    env = {k:old['environment'][k] for k in ('COMSPEC','PATHEXT','SYSTEMROOT','WINDIR','PYTHONDONTWRITEBYTECODE','PYTHONUNBUFFERED','OKTO_NEXUS_NO_BANNER','OKTO_NEXUS_CONNECTOR_VAULT')}
    env.update(USERPROFILE=str(ROOT/'profile'), APPDATA=str(ROOT/'profile/appdata'), LOCALAPPDATA=str(ROOT/'profile/localappdata'), TEMP=str(ROOT/'profile/tmp'), TMP=str(ROOT/'profile/tmp'), PATH=str(Path(sys.executable).parent)+';C:/Python313;C:/WINDOWS/System32')
    return old, env

def commands(old):
    mapping = {old['python']:sys.executable, old['server_home']:str(ROOT/'nexus'), old['connector_state']:str(ROOT/'connector'), old['project_root']:str(ROOT/'project'), '52106':'58741'}
    return {(s['component'],s['action']):[mapping.get(x,x) for x in s['argv']] for s in old['steps'] if s['action'] in ('install','enable','uninstall')}

def cli(label, argv, env):
    require('--force' not in argv and 'start' not in argv, 'UNEXPECTED_ACTION')
    save(PRIVATE/(label+'.reserved.json'), {'argv':argv, 'at':time.time()})
    with (PRIVATE/(label+'.stdout')).open('xb') as out, (PRIVATE/(label+'.stderr')).open('xb') as err:
        child = subprocess.Popen(argv, env=env, cwd=ROOT/'project', stdin=subprocess.DEVNULL, stdout=out, stderr=err, creationflags=subprocess.CREATE_NO_WINDOW)
        save(PRIVATE/(label+'.process.json'), {'pid':child.pid})
        code = child.wait()
    data = json.loads((PRIVATE/(label+'.stdout')).read_bytes())
    safe_keys = {'state','reason','enabled','changed','installed','already_installed','uninstalled','data_preserved','instance_id','pid','generation','process_action','running','status','error','code','stage','result','installation_state'}
    def projection(v):
        if isinstance(v,dict): return {k:projection(x) for k,x in v.items() if k in safe_keys}
        if isinstance(v,list): return [projection(x) for x in v]
        return v
    report = {'label':label,'returncode':code,'wrapper_exit_confirmed':True,'result':projection(data),
        'stdout_sha256':sha(PRIVATE/(label+'.stdout')),'stderr_sha256':sha(PRIVATE/(label+'.stderr'))}
    save(PUBLIC/(label+'.json'), report)
    print(json.dumps(report), flush=True)
    return code, data

def native(service):
    task = service.tasks.read(service.name)
    if task is None: return {'name':service.name,'absent':True}
    require(not task.active and task.state not in (0,2,4), 'UNEXPECTED_ACTIVE_TASK')
    return {'name':service.name,'absent':False,'digest':task.digest,'state':task.state,'enabled':task.enabled,'last_result':task.last_result}

def execute():
    package_proof = pins()
    old, env = configure()
    require(not (PUBLIC/'started.json').exists(), 'ALREADY_SELECTED')
    os.environ.clear(); os.environ.update(env)
    from okto_nexus.adapters.outbound.service_manager.installation import ServerInstallation
    from okto_nexus_connector.platform.user_service import UserService
    services = {'nexus':ServerInstallation(ROOT/'nexus', ROOT/'nexus/nexus.db'), 'connector':UserService(ROOT/'connector')}
    argv = commands(old)
    before = {k:native(s) for k,s in services.items()}
    require(all(v['absent'] for v in before.values()), 'TASK_ALREADY_EXISTS')
    require(all(not any((ROOT/n).iterdir()) for n in ('nexus','connector','project')), 'HOME_NOT_EMPTY')
    save(PUBLIC/'started.json', {'packages':package_proof,'source_sha256':sha(__file__),'before':before,'provider_calls':0,'service_starts':0,'at':time.time()})
    results = {}
    for name, service in services.items():
        code,_ = cli(name+'-install1', argv[name,'install'], env)
        require(code == 0, 'INSTALL_FAILED')
        original = service.tasks.read(service.name)
        first = native(service)
        receipt_path = service.path if name == 'nexus' else ROOT/'connector/service-installation.json'
        # XML contains the temporary ownership token: retain only in protected storage.
        (PRIVATE/(name+'-original.xml')).write_text(original.xml,encoding='utf-8')
        receipt_hash = sha(receipt_path)
        for label, action in (('install2','install'),('enable1','enable'),('enable2','enable')):
            code,_ = cli(name+'-'+label, argv[name,action], env)
            require(code == 0 and native(service) == first and sha(receipt_path) == receipt_hash, 'REPEATED_OPERATION_CHANGED_TASK')
        ns = {'t':'http://schemas.microsoft.com/windows/2004/02/mit/task'}
        ET.register_namespace('', ns['t'])
        tree = ET.fromstring(original.xml)
        node = tree.find('t:RegistrationInfo/t:Description', ns)
        require(node is not None, 'DESCRIPTION_NOT_FOUND')
        node.text = (node.text or '') + ' [SVC-T17 owned temporary external edit]'
        edited_xml = ET.tostring(tree, encoding='unicode')
        save(PRIVATE/(name+'-external-edit.reserved.json'),{'expected_digest':original.digest,'task_name':service.name})
        changed = service.tasks.replace(service.name, original.digest, edited_xml)
        require(changed.digest != original.digest, 'EXTERNAL_EDIT_NOT_APPLIED')
        edited = native(service)
        save(PUBLIC/(name+'-external-edit.json'),{'before':first,'after':edited,'changed_field':'RegistrationInfo/Description','service_not_started':True})
        for action in ('enable','uninstall'):
            code,value = cli(name+'-'+action+'-changed',argv[name,action],env)
            require(code != 0 and 'SERVICE_DEFINITION_CHANGED' in json.dumps(value), 'EXTERNAL_EDIT_NOT_REFUSED')
            require(native(service) == edited and sha(receipt_path) == receipt_hash, 'EXTERNAL_EDIT_NOT_PRESERVED')
        save(PRIVATE/(name+'-restore.reserved.json'),{'expected_digest':changed.digest,'restore_digest':original.digest,'task_name':service.name})
        restored = service.tasks.replace(service.name, changed.digest, original.xml)
        require(restored.digest == original.digest and native(service) == first, 'RESTORATION_UNCONFIRMED')
        code,_ = cli(name+'-uninstall',argv[name,'uninstall'],env)
        require(code == 0 and native(service)['absent'], 'CLEANUP_UNCONFIRMED')
        results[name] = {'repeated_install_and_enable_unchanged':True,'external_definition_preserved_on_enable_and_uninstall':True,'original_definition_restored':True,'task_absent':True,'service_starts':0,'provider_calls':0}
    require(pins() == package_proof, 'PACKAGES_CHANGED')
    save(PUBLIC/'qualification.json',{'status':'PASS','scenario':'SVC-T17','hosts':results,'package_proof':package_proof,'completed_at':time.time(),'limits':['Windows Task Scheduler registration and preservation only.','No login, service startup, provider call or other scenario acceptance.']})
    print(json.dumps({'status':'PASS','scenario':'SVC-T17','tasks_absent':True}),flush=True)

if __name__ == '__main__':
    try:
        require(sys.argv[1:] == ['execute'], 'EXPLICIT_EXECUTE_REQUIRED')
        execute()
    except Exception as error:
        value = {'status':'STOPPED','error':str(error) if isinstance(error,ValueError) else type(error).__name__,'no_automatic_replay':True}
        if PUBLIC.exists(): save(PUBLIC/'failure.json',value)
        print(json.dumps(value),flush=True)
        raise SystemExit(1)
