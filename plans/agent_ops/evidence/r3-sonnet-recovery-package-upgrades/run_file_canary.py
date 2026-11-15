from pathlib import Path
import tempfile,sys,json,uuid,hashlib
import win32security,win32api,win32con,ntsecuritycon
C=Path('C:/Users/jpamb/AppData/Local/Temp/m1-sonnet-remote-candidate-2c_4af0t');sys.path.insert(0,str(C))
from reused_observation import secure_directory
from okto_nexus_connector.identity.vault import RestrictedFileVault
import okto_nexus_connector.identity.vault as module
B=Path(tempfile.mkdtemp(prefix='sonnet-file-vault-canary-'));root=secure_directory(B/'vault',B)
t=win32security.OpenProcessToken(win32api.GetCurrentProcess(),win32con.TOKEN_QUERY)
try:user=win32security.GetTokenInformation(t,win32security.TokenUser)[0]
finally:t.Close()
system=win32security.CreateWellKnownSid(win32security.WinLocalSystemSid,None)
expected={win32security.ConvertSidToStringSid(s) for s in (user,system)}
def check(path):
 path=Path(path).resolve();assert path.is_relative_to(root.resolve())
 assert not win32api.GetFileAttributes(str(path))&win32con.FILE_ATTRIBUTE_REPARSE_POINT
 sd=win32security.GetNamedSecurityInfo(str(path),win32security.SE_FILE_OBJECT,win32security.DACL_SECURITY_INFORMATION);acl=sd.GetSecurityDescriptorDacl();assert acl and acl.GetAceCount()==2
 seen=set()
 for i in range(acl.GetAceCount()):
  hdr,mask,sid=acl.GetAce(i);assert hdr[0]==0 and mask==ntsecuritycon.FILE_ALL_ACCESS;seen.add(win32security.ConvertSidToStringSid(sid))
 assert seen==expected
 return {'path_role':'temporary' if path.name.startswith('.secrets-') else 'final','exact_current_user_system_full_control':True,'inherited':all(acl.GetAce(i)[0][1]&16 for i in range(2))}
original=module.os.replace;checks=[]
def replace(src,dst):
 checks.append(check(src));original(src,dst);checks.append(check(dst))
module.os.replace=replace
v=RestrictedFileVault(root,approved=True);sentinel='synthetic-'+uuid.uuid4().hex;namespace='synthetic-only';result={}
try:
 handle=v.store(namespace,sentinel);result['roundtrip']=v.resolve(handle)==sentinel;assert result['roundtrip']
finally:
 v.remove(namespace);module.os.replace=original
assert json.loads((root/'secrets.json').read_bytes())=={}
result.update(status='PASS',scope='NEW_TEMP_SYNTHETIC_ONLY',real_own_vault_touched=False,temporary_and_final_acl_checks=checks,sentinel_removed=True,file_empty_after_removal=True,source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),helper_sha256=hashlib.sha256((C/'reused_observation.py').read_bytes()).hexdigest())
(B/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'result_path':str(B/'result.json'),'result_sha256':hashlib.sha256((B/'result.json').read_bytes()).hexdigest(),**result}))
