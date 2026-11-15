from pathlib import Path
from datetime import datetime,timezone,timedelta
from copy import deepcopy
import sys,unittest
sys.path.insert(0,str(Path(__file__).parent))
import grant_preflight as g
class Tests(unittest.TestCase):
    def test_readonly_review_scope_balance_and_time(self):
        now=datetime.now(timezone.utc)
        scope={k:k for k in ('server_id','executor_id','binding_id','workspace_binding_id','workspace_id','agent_id')}
        grant={'grant_id':g.GRANT,'state':'available','max_executions':3,'used_executions':0,
            'actions':sorted(g.ACTIONS),'expires_at':(now+timedelta(seconds=700)).isoformat()}
        review={'state':'authorization_review','scope':scope,'current_grants':[grant],
            'has_more_grants':False,'total_grants':1,'actions':sorted(g.ACTIONS)}
        calls=[]
        class Flow:
            def api(self,*args):calls.append(args);return deepcopy(review)
        self.assertEqual(g.check(Flow(),scope,'useful','request07')['remaining_actions'],3)
        self.assertEqual(calls,[('POST','/connections/authorizations:review',{'binding_id':'binding_id',
            'client_request_id':'request07-readonly-grant-preflight','minutes':60,'max_executions':3})])
        for field,value in [('state','expired'),('grant_id','other'),('actions',['open']),('used_executions',2),
                             ('expires_at',(now+timedelta(seconds=599)).isoformat())]:
            changed=deepcopy(review);changed['current_grants'][0][field]=value
            with self.subTest(field=field),self.assertRaises(RuntimeError):g.validate(changed,scope,'useful',now)
        changed=deepcopy(review);changed['scope']['binding_id']='other'
        with self.assertRaises(RuntimeError):g.validate(changed,scope,'useful',now)
        changed=deepcopy(review);changed['current_grants'][0]['used_executions']=2
        self.assertEqual(g.validate(changed,scope,'continuation',now)['remaining_actions'],1)
if __name__=='__main__':unittest.main(verbosity=2)
