"""Correct inherited v10 six-turn fixture to v11 selected one-setup/four-work allocation."""
from pathlib import Path
import json,hashlib,difflib
R=Path(__file__).resolve().parent;D=R/'draft';P=D/'controller/test_independent.py'
original=(R/'observer-composition-initial/sources/controller/test_independent.py').read_text();changed=original
old="        control.setup('setup-remote','local',home,lambda:dispatches.append('setup-remote'),lambda:stop.append('local'))\n        setups.append(setup_journal(home,2,300));assert control.poll()['can_admit']\n"
assert changed.count(old)==1
changed=changed.replace(old,"        # Selected v11 remote bootstrap has zero productive model turns.\n        assert control.poll()['can_admit']\n")
changed=changed.replace('test_one_global_ledger_across_setup_local_continuation_reopen_remote_setup_and_work','test_one_global_ledger_across_one_setup_local_continuation_reopen_remote_work')
for old,new in [("summary['new_reserved_requests']==6","summary['new_reserved_requests']==5"),
    ("POLICY['carry_in_tokens']+200+300+20+40","POLICY['carry_in_tokens']+200+20+40"),
    ("dispatches==['setup-local','setup-remote']","dispatches==['setup-local']"),
    ("control.start_work('seventh'","control.start_work('sixth'"),
    ("control.summary()['new_reserved_requests']==6","control.summary()['new_reserved_requests']==5")]:
    assert old in changed;changed=changed.replace(old,new)
P.write_bytes(changed.encode())
(D/'diffs/test_independent.v11-nominal-fixture.diff').write_bytes(''.join(difflib.unified_diff(original.splitlines(True),changed.splitlines(True),fromfile='initial-v11/test_independent.py',tofile='corrected-v11/test_independent.py')).encode())
records=json.loads((D/'observer-rebase-map.json').read_bytes())
key=next(key for key in records if key.replace('\\','/')=='controller/test_independent.py')
records[key]['sha256']=hashlib.sha256(P.read_bytes()).hexdigest()
records[key]['change']='Actual selected v11 allocation: one productive local setup and four work requests; no productive remote bootstrap; five requests total.'
(D/'observer-rebase-map.json').write_bytes((json.dumps(records,indent=2)+'\n').encode())
source=R/'observer-composition-initial/pytest-tmp/test_actual_five_requests_roun0/controller.json'
v=json.loads(source.read_bytes())
evidence={'status':'OBSERVED_TIMING_LIMITATION_FAIL_CLOSED','original_suite':'observer-composition-initial/results.xml',
    'policy_case':'Five work requests for allocation ceiling, not selected nominal one-setup/four-work route.',
    'faults':v['faults'],'first_errors':{name:value['first_observation_error'] for name,value in v['requests'].items() if 'first_observation_error' in value},
    'reserved':len(v['requests']),'observation':v['independent_observation'],
    'runtime_changed':False,'budget_changed':False,'later_pass_erases_failure':False}
(D/'v11-initial-timing-failure.json').write_bytes((json.dumps(evidence,indent=2)+'\n').encode())
print('Corrected inherited fixture only; runtime and failure evidence preserved.')
