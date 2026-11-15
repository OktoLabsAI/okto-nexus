from pathlib import Path
from datetime import datetime,timezone,timedelta
import importlib.util,json,sys,unittest
H=Path(__file__).parent;sys.path.insert(0,str(H))
manifest=json.loads((H/'work-runtime-freeze.json').read_bytes())
dependency=Path(manifest['dependencies']['cli_flow.py']['path'])
sys.path.insert(0,str(dependency.parent))
import cli_flow
import grant_preflight as g
from okto_nexus.application.terminal_connection import PREFIX
class Test(unittest.TestCase):
 def test_real_adapter_get_only_and_public_transport_review(self):
  calls=[];scope={k:k for k in ('server_id','executor_id','binding_id','agent_id','workspace_id','workspace_binding_id')}
  value={'state':'authorization_review','scope':scope,'has_more_grants':False,'total_grants':1,'actions':sorted(g.ACTIONS),
   'current_grants':[{'grant_id':g.GRANT,'state':'available','max_executions':3,'used_executions':0,'actions':sorted(g.ACTIONS),
    'expires_at':(datetime.now(timezone.utc)+timedelta(seconds=700)).isoformat()}]}
  flow=object.__new__(cli_flow.CLIFlow);flow._command_readonly=False
  flow._raw=lambda *args:(calls.append(args),value)[1];flow.call=flow._dispatch
  with self.assertRaisesRegex(ValueError,'READ_ONLY_API_REQUIRED'):flow.api('POST','/connections/authorizations:review',{})
  self.assertEqual(calls,[])
  self.assertEqual(g.check(flow,scope,'useful','request07')['remaining_actions'],3)
  self.assertEqual(calls,[('POST',PREFIX+'/connections/authorizations:review',{'binding_id':'binding_id',
   'client_request_id':'request07-readonly-grant-preflight','minutes':60,'max_executions':3})])
if __name__=='__main__':unittest.main(verbosity=2)
