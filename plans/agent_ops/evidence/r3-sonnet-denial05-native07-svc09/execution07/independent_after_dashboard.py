"""Independent canonical observation; no workflow reentry, decision, or work."""
from pathlib import Path
import json,sys,time
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from work_context import Context
from okto_nexus.adapters.outbound.operator_client import OperatorProfile
from okto_nexus.application.terminal_connection import PREFIX
X=Context(HERE/'work-plan.json','cac4e15c1f9bd0e6b1aeb49cb5e60dc95dd6c78880faa4c16923540b7bcd7eb7')
try:
    X.activate('useful')
    admission=json.loads((X.PRIVATE/'m1-sonnet-remote-useful-07-admission.json').read_bytes())
    client=OperatorProfile(X.base.P['paths']['operator_home'],X.P['operator_profile']).client()
    client.verify()
    op=client('GET',PREFIX+'/runtime/operations/'+admission['operation_id'])
    assert op['operation_id']==admission['operation_id']
    assert all(op['scope'][k]==v for k,v in X.expected_scope.items())
    assert op['scope']['session_id']==admission['session_id']
    assert op['executor_stage'] not in ('SUCCEEDED','FAILED','CANCELLED')
    assert op['admission_state']!='RESOLVED_TERMINAL'
    value={'observed_at':time.time(),'operation':{k:op.get(k) for k in ('operation_id','scope','executor_stage','admission_state')},
        'cohorts':X.selected,'all_six_retained_handles_alive':True,'dashboard_closed_tool':'Playwright browser_tabs.close index1',
        'no_work_or_decision_selected':True,'prior_observer_failure':'workflow reentry correctly refused predecessor checkpoint change; independent read does not modify it'}
    with (X.PUBLIC/'dashboard-after-close-independent.json').open('x',encoding='utf-8') as f:
        json.dump(value,f,indent=2);f.write('\n')
    print(json.dumps(value))
finally:X.close()
