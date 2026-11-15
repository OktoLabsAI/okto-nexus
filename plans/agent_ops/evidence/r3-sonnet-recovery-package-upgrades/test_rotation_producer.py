from pathlib import Path
import sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parent))
from rotation_producer import produce
class X:
 def __init__(self,fail=None):self.saved={};self.guards=0;self.fail=fail
 def preflight(self,_):
  self.guards+=1
  if self.guards==self.fail:raise RuntimeError('FIXTURE_FENCE')
 def save(self,name,value):
  if name in self.saved:raise RuntimeError('ALREADY_RESERVED')
  self.saved[name]=value
class Tests(unittest.TestCase):
 def post(self,calls,response=None):
  def call(*args):calls.append(args);return response or {'ok':True,'data':{'agent_id':'m1-sonnet-remote','api_key':'nxs_'+'a'*48}}
  return call
 def test_success_once_and_no_replay(self):
  x=X();calls=[];sent=[];produce(x,self.post(calls),sent.append)
  self.assertEqual((len(calls),len(sent)),(1,1))
  self.assertNotIn('api_key',str(x.saved))
  with self.assertRaises(RuntimeError):produce(x,self.post(calls),sent.append)
  self.assertEqual(len(calls),1)
 def test_unknown_consumes_reservation_never_retries(self):
  x=X();calls=[]
  def unknown(*args):calls.append(args);raise TimeoutError('fixture')
  with self.assertRaises(TimeoutError):produce(x,unknown,lambda _:self.fail())
  with self.assertRaises(RuntimeError):produce(x,unknown,lambda _:self.fail())
  self.assertEqual(len(calls),1)
 def test_second_fence_before_post(self):
  x=X(fail=2);calls=[]
  with self.assertRaises(RuntimeError):produce(x,self.post(calls),lambda _:self.fail())
  self.assertFalse(calls);self.assertIn('rotation-post-reserved.json',x.saved)
 def test_first_fence_no_reservation(self):
  x=X(fail=1)
  with self.assertRaises(RuntimeError):produce(x,lambda *_:self.fail(),lambda _:self.fail())
  self.assertFalse(x.saved)
 def test_wrong_identity_never_emitted(self):
  x=X();calls=[]
  with self.assertRaises(RuntimeError):produce(x,self.post(calls,{'ok':True,'data':{'agent_id':'other','api_key':'nxs_'+'a'*48}}),lambda _:self.fail())
  self.assertEqual(len(calls),1);self.assertNotIn('rotation-material-emitted.json',x.saved)
 def test_invalid_key_never_emitted(self):
  x=X();calls=[]
  with self.assertRaises((RuntimeError,TypeError)):produce(x,self.post(calls,{'ok':True,'data':{'agent_id':'m1-sonnet-remote','api_key':'invalid'}}),lambda _:self.fail())
  self.assertEqual(len(calls),1)
if __name__=='__main__':unittest.main(verbosity=2)
