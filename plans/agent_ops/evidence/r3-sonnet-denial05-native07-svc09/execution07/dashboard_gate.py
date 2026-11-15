from pathlib import Path
import csv,json,sys,time
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from work_context import Context
X=Context(HERE/'work-plan.json','cac4e15c1f9bd0e6b1aeb49cb5e60dc95dd6c78880faa4c16923540b7bcd7eb7')
try:
    X.activate('useful')
    admission=json.loads((X.PRIVATE/'m1-sonnet-remote-useful-07-admission.json').read_bytes())
    value=X._console_observation(admission['operation_id'])
    assert value['executor_stage'] not in ('SUCCEEDED','FAILED','CANCELLED')
    assert value['admission_state']!='RESOLVED_TERMINAL'
    value.update(observed_at=time.time(),cohorts_active=True,browser_url='http://127.0.0.1:58631/',
        no_new_model_requests=True,stage=sys.argv[1])
    with (X.PUBLIC/('dashboard-'+sys.argv[1]+'.json')).open('x',encoding='utf-8') as f:
        json.dump(value,f,indent=2);f.write('\n')
    if sys.argv[1]=='before-close':
        rows=list(csv.reader(Path(X.P['input_fixture']['path']).read_text(encoding='utf-8-sig').splitlines()))
        value['fixture_shape']={'header':rows[0],'column_counts':[len(r) for r in rows[1:]]}
    print(json.dumps(value))
finally:X.close()
