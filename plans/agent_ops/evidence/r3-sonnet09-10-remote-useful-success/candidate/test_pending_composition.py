from pathlib import Path
from types import SimpleNamespace
from concurrent.futures import Future
import json,sys,unittest,tempfile
H=Path(__file__).parent;sys.path.insert(0,str(H))
import successor_policy as p
from sonnet_usage import restore_budget
class Tests(unittest.TestCase):
 def test_dashboard_liveness_requires_positive_states(self):
  from dashboard_observer import same_active_operation
  self.assertIs(same_active_operation({'executor_stage':'SUBMITTED','admission_state':'DISPATCHED'}),True)
  for value in ({},{'executor_stage':'unknown','admission_state':'DISPATCHED'},{'executor_stage':'SUBMITTED'}):
   self.assertIsNone(same_active_operation(value))
  self.assertIs(same_active_operation({'executor_stage':'CANCELLED','admission_state':'RESOLVED_TERMINAL'}),False)
 def test_pending_authority_creates_no_paid_plan_or_new_seed(self):
  from materialize import materialize
  with self.assertRaisesRegex(RuntimeError,'AUTHORIZATION_PENDING'):materialize(H/'authorization-record.json')
  self.assertFalse((H/'work-plan.json').exists());self.assertFalse((H/'budget-seed-approved.json').exists());self.assertFalse((H/'paid-work').exists())
 def test_in_memory_authorized_policy_preserves_three_rows_and_finite_headroom(self):
  candidate=json.loads((H/'candidate.json').read_bytes());seed=json.loads(Path(candidate['current_seed']['path']).read_bytes())
  record={'explicit_user_approval':True,'user_response':'synthetic-only','response_reference':'fixture-only',
      'policy':p.POLICY,'carry_tokens':180426,'native_charges':3,'server_admissions':4}
  derived=p.convert(seed,record,candidate)
  self.assertEqual(derived['state']['sessions'],seed['state']['sessions'])
  budget=restore_budget(derived);self.assertEqual((budget.known,budget.max_requests),(180426,5))
  self.assertEqual(budget.check_admission('useful')['reserved_next'],244846)
  self.assertEqual(budget.check_admission('continuation')['reserved_next'],138423)
  self.assertEqual(budget.reservation_estimate('setup'),244846)
  p.validate_history(budget,derived)
 def test_empty_event_pages_still_refresh_pending_callback(self):
  from observe_active import observe_active
  ledger=SimpleNamespace(cursor=0,active='op',scope={'session_id':'s','stream_epoch':'e'},faults=[],known=0,preventive=480000)
  ledger.summary=lambda:{'faults':list(ledger.faults)}
  monitor=SimpleNamespace(started_at=0,observed_at=0,freshness=20,budget=None)
  monitor.observed=lambda:None;monitor.containment=lambda **kw:'TEST_CONTAINED'
  class Flow:
   def events(self,**kw):return {'events':{'events':[]}}
  class Worker:
   def submit(self,fn,**kw):
    f=Future();f.set_result(fn(**kw));return f
  calls=[]
  def pending(value):
   calls.append(value)
   if len(calls)==2:ledger.faults.append('TEST_STOP')
  result=observe_active(flow=Flow(),worker=Worker(),ledger=ledger,monitor=monitor,owner_observation=lambda:{},
   interrupt=lambda *a:None,publish=lambda v:None,clock=lambda:0,sleep=lambda n:None,on_page=pending)
  self.assertEqual(len(calls),2);self.assertEqual(result['state'],'OBSERVATION_FAULT')
if __name__=='__main__':unittest.main(verbosity=2)
