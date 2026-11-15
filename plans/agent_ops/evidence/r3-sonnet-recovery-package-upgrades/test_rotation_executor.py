from pathlib import Path
import sys,unittest,tempfile,json,hashlib
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
import rotation_executor as E
class Fake:
 def __init__(self,epoch=2):
  self.saved={};self.guards=[];self.python='fixture-python';self.plan_sha='fixture';self.authorization_sha='fixture'
  self.ROOT=Path(tempfile.mkdtemp(prefix='rotation-executor-test-'))
  p=Path(__file__).parent/'rotation_producer.py'
  self.P={'runtime_pins':{'rotation_producer.py':{'path':str(p),'sha256':E.sha(p)}},'paths':{'connector_state':str(self.ROOT/'state'),'server_home':str(self.ROOT/'home')},'origin':'http://127.0.0.1:58631'}
  self.base=SimpleNamespace(env=lambda:{},require_ready=lambda:True)
  self.identity=SimpleNamespace(agent_id=E.AGENT,server_id=E.SERVER,credential_epoch=epoch,revoked=False)
 def state(self):return SimpleNamespace(identity_by_alias=lambda _:self.identity)
 def consumer_env(self):return {'OKTO_NEXUS_CONNECTOR_VAULT':'file'}
 def preflight(self,phase):self.guards.append(phase);return True
 def save(self,name,value):
  if name in self.saved:raise RuntimeError('ALREADY_RESERVED')
  self.saved[name]=value
SUCCESS={'status':'TRANSFERRED_ONCE','producer_exit':0,'consumer_exit':0,'active_job_processes_after':0,'forced_owned_cleanup':False,'effect_guard_required':True,'effect_gates_allowed':['producer','consumer'],'public_ipc_readers_joined':True}
class Tests(unittest.TestCase):
 def test_authority_exact_fields(self):
  a={'rotation_plan_sha256':'p','status':'SPECIFIC_EXCEPTION_AUTHORIZED','agent_id':E.AGENT,'revoke_lost_epoch':1,'plaintext_file_path':'ownpath','user_authorization_reference':'fixture-only-not-a-receipt'}
  E.validate_authorization(a,'p','ownpath')
  for key in a:
   bad=dict(a);bad.pop(key)
   with self.subTest(key=key),self.assertRaises(RuntimeError):E.validate_authorization(bad,'p','ownpath')
 def test_transfer_success_explicit_epoch_and_no_replay(self):
  x=Fake();calls=[]
  def helper(**kw):
   calls.append(kw);self.assertIn('--non-interactive',kw['consumer_argv']);self.assertEqual(kw['consumer_env']['OKTO_NEXUS_CONNECTOR_VAULT'],'file');return SUCCESS
  with patch.object(E,'canonical_epoch',return_value=2),patch.object(E,'check_vault_acl',return_value=[]):
   E.transfer(x,helper)
   with self.assertRaises(RuntimeError):E.transfer(x,helper)
  self.assertEqual(len(calls),1);self.assertEqual(x.saved['rotation-import-result.json']['current_epoch'],2)
 def test_wrong_local_epoch_blocks_complete(self):
  x=Fake(epoch=1)
  with patch.object(E,'canonical_epoch',return_value=2),patch.object(E,'check_vault_acl',return_value=[]),self.assertRaises(RuntimeError):E.transfer(x,lambda **_:SUCCESS)
  self.assertNotIn('rotation-import-result.json',x.saved)
 def test_unknown_transfer_preserved_not_completed(self):
  x=Fake();value=dict(SUCCESS,status='UNCONFIRMED',consumer_exit=1)
  with self.assertRaises(RuntimeError):E.transfer(x,lambda **_:value)
  self.assertEqual(x.saved['rotation-protected-transfer-result.json']['status'],'UNCONFIRMED');self.assertNotIn('rotation-import-result.json',x.saved)
 def test_reparse_rejected_before_acl_or_resolve(self):
  import win32api,win32security,win32con
  root=Path(tempfile.mkdtemp(prefix='rotation-reparse-fixture-'));state=root/'state';state.mkdir()
  with patch.object(win32api,'GetFileAttributes',return_value=win32con.FILE_ATTRIBUTE_REPARSE_POINT),patch.object(win32security,'GetNamedSecurityInfo') as acl,self.assertRaises(RuntimeError):E.check_vault_acl(state,root)
  acl.assert_not_called()
if __name__=='__main__':unittest.main(verbosity=2)
