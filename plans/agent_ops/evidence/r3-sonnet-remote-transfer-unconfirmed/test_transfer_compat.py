from pathlib import Path
import sys,json,hashlib,unittest
from types import SimpleNamespace
C=Path(__file__).resolve().parent
sys.path.insert(0,str(C))
import connector_lifecycle_compat as L
from transfer_compat_context import verify_compat
class Checks(unittest.TestCase):
 def test_canonical_filetime(self):
  self.assertEqual(L.normalize_identity({'pid':45204,'birth_token':'filetime:134391687599588237'}),{'pid':45204,'birth':134391687599588237})
 def test_invalid_tokens(self):
  for token in [None,'filetime:0','filetime:01','filetime:-1','filetime:1.0','filetime:١','filetime:+1','1']:
   with self.subTest(token=token),self.assertRaises(Exception):L.normalize_identity({'pid':1,'birth_token':token})
 def test_birth_mismatch_closes_handles(self):
  c=dict(phase='running',child_acknowledged=True,cycle_id='fixture',attempts_started=1,**{r:dict(pid=1,birth=2) for r in L.ROLES})
  handles=[]
  class H:
   birth=3;image='fixture'
   def __init__(self,pid):self.closed=False;handles.append(self)
   def close(self):self.closed=True
  with self.assertRaises(Exception):L.capture(SimpleNamespace(installed={'python_images':{}}),observe=lambda *_:dict(pid=1),read_cycle=lambda _:c,process=H)
  self.assertEqual(len(handles),1);self.assertTrue(handles[0].closed)
 def test_original_and_new_pins(self):
  self.assertTrue(verify_compat()['original_failure_preserved'])
if __name__=='__main__':
 result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Checks))
 out={'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'real_services_queried':False,'actual_capture_deferred_to_root_select':True,'manifest_sha256':hashlib.sha256((C/'transfer-compat-manifest.json').read_bytes()).hexdigest()}
 (C/'transfer-compat-qualification.json').write_text(json.dumps(out,indent=2)+'\n')
 raise SystemExit(not result.wasSuccessful())
