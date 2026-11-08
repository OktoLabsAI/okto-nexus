"""Freeze offline candidate inputs; never install or authorize the campaign."""
from pathlib import Path
import difflib,hashlib,json
R=Path(__file__).resolve().parent;D=R/'draft'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
read=lambda p:json.loads(Path(p).read_bytes())
def write(p,v):p.write_bytes((json.dumps(v,indent=2,ensure_ascii=False)+'\n').encode())
p=read(D/'m1-codex-campaign-proposal-v10.json')
recipe=Path(r'C:/Users/jpamb/AppData/Local/Temp/m1-v10-readonly-remote-recipe-9eitvld7/recipe.json')
assert sha(recipe)=='2e69496b8da1e0453b598917a9f28d5b4f7a3fc263f5b554effcc58d448f8f93'
target=D/'remote-canonical-recipe.json'
with target.open('xb') as stream:stream.write(recipe.read_bytes())
planning=read(D/'planning-commands.json')
planning['status']='FROZEN_REFERENCE_COMMANDS_REQUIRING_EXACT_V10_APPROVAL'
planning['remote_recipe']={'path':str(target),'sha256':sha(target)}
write(D/'planning-commands.json',planning)
commands=read(D/'proposed-commands.json')
commands['status']='FROZEN_EIGHT_ACTIONS_REQUIRING_EXACT_V10_APPROVAL'
commands['execution_authorized']=False
write(D/'proposed-commands.json',commands)
files=p['execution_bundle']['files']
for key,name in [('remote_stop_order','remote_stop_order.py'),('remote_transfer_monitor','remote_transfer_monitor.py'),
                 ('remote_setup','m1_v10_remote_setup.py'),('planning_commands','planning-commands.json'),
                 ('remote_canonical_recipe','remote-canonical-recipe.json')]:
    files[key]={'path':str(D/name),'sha256':sha(D/name)}
for key,value in files.items():
    if Path(value['path']).is_relative_to(D):value['sha256']=sha(value['path'])
    else:assert sha(value['path'])==value['sha256']
p['execution_bundle']['commands']={'path':str(D/'proposed-commands.json'),'sha256':sha(D/'proposed-commands.json')}
p['status']='PREPARED_FOR_ROOT_REVIEW_NOT_AUTHORIZED'
p['qualification_status']='OFFLINE_COMPOSITION_QUALIFIED_FINAL_GATES_RECORDED_SEPARATELY'
p['blocking_preconditions']=['Root independent review of the frozen proposal and bundle.',
    'Explicit new user approval for this exact successor proposal; no approval receipt exists.',
    'After approval: recheck exact own task absence/port/homes/native pins, then one timed offline product installation.']
p['controller_preparation']['status']='V10_COMPOSED_SYNTHETIC_QUALIFIED'
p['controller_preparation']['qualification_status']='26_V10_COMPOSITION_CASES_PASS_NO_PROVIDER'
p['controller_preparation']['composed_module_origins']={'path':str(R/'observer-composition-initial/module-origins.json'),
    'sha256':sha(R/'observer-composition-initial/module-origins.json')}
p['controller_preparation']['operational_limit']='Bounded SQLite readers and an independent API worker keep accounting off HTTP. A scheduling gap over one second latches a fault and prevents new effects; no real-time OS guarantee. Earlier source combined 44 PASS/3 FAIL scheduling/SQLite attempt is retained; later 25 composition +1 deterministic cadence test passed. This v10 composition passed 26 synthetic cases.'
p['execution_bundle']['status']='FROZEN_QUALIFIED'
p['execution_bundle']['gate']='All effects require a real exact v10 approval receipt, unchanged module/product/native hashes and a successful one-shot installation receipt. No approval receipt or installation reservation exists.'
p['execution_bundle']['qualification_scope']='Offline only: 26 actual v10 observer/work composition cases; 16 monitor cases plus 6 whole remote wrapper cases with fake effects; 20 separately qualified benign PTY cases. Final entry denials and unchanged fake installer regressions are reported separately. No claim of successful real M1 work.'
p['execution_bundle']['final_gate_reports']=[str(R/'final-entry-gates/results.xml'),str(R/'final-entry-gates/result.json')]
p['execution_bundle']['normal_stop_once']='Controller selection remains one shared normal-stop reservation per admitted owner. During remote transfer callbacks only persist selection. Both service stops are selected after any verified-remote failure, including a Connector with no work record. Dispatch waits for retained helper join, exact Job0 and reader join, then uses each existing lifecycle stop receipt once; one lane spawn error does not block the other. Native exit still requires external owner/task proof.'
p['execution_bundle']['remote_transfer_order']={'phase_deadline_seconds':120,'maximum_poll_start_gap_seconds':1,
    'cadence_miss_fault':'REMOTE_MONITOR_CADENCE_EXCEEDED','effect_gates':['producer','consumer'],
    'new_token_reservations':0,'historical_observers_reattached':True,
    'stop_order_module':files['remote_stop_order'],
    'conservative_limit':'Helper dispatch is reserved before transfer preflight. A refusal before worker start can therefore leave helper state conservatively UNKNOWN; no replay or automatic stop release follows without reconciliation.',
    'scheduler_limit':'Job0 proves the consumer cannot later rewrite desired=running. A Scheduler request already accepted is outside the Job: canonical stop latches desired=draining under launch_exclusion, and same-logon service_process refuses it. Stop return alone is never proof of task/process exit.'}
p['execution_bundle']['pty']['helper_revision']='v10 explicit producer/consumer owner gates; immutable v5 is not modified'
p['execution_bundle']['pty']['qualification']='20 unique benign cases PASS, no product CLI/provider/service; helper SHA and 12 external dependency payloads pinned'
p['finite_work']['allocation']='At most six new conservative reservations remain within eleven cumulative. Nominal selected path uses five new productive admissions: one local setup test plus four work requests. The qualified remote bootstrap/key-transfer helper performs zero productive model turns; its unused sixth allowance is not reassigned or retried.'
invariants=p['token_accounting']['required_invariants']
p['token_accounting']['required_invariants']=[
    'Accounting uses bounded exact own-journal readers independently of the serialized API worker and preserves the first sanitized error.' if 'pending qualification' in s else s for s in invariants]
p['base06_installation']['status']='DEPENDENCIES_ONLY_PREPARED_PRODUCTS_REQUIRE_EXACT_APPROVAL'
p['execution_authorized']=False
p['authorization']['execution_authorized']=False
preflight=R/'root-readonly-preflight.json'
if preflight.exists():
    p['readonly_preflight']={'path':str(preflight),'sha256':sha(preflight),'runtime_recheck_required':True,
        'meaning':'Historical read-only task/port/native snapshot; no reservation or execution authority.'}
write(D/'m1-codex-campaign-proposal-v10.json',p)
previous=Path(r'C:/Users/jpamb/AppData/Local/Temp/m1-v9-preparation-t4xaqhca/draft/m1_v9_remote_setup.py')
(D/'diffs/remote_setup.final.diff').write_bytes(''.join(difflib.unified_diff(previous.read_text().splitlines(True),
    (D/'m1_v10_remote_setup.py').read_text().splitlines(True),fromfile='v9/remote_setup.py',tofile='v10/remote_setup.py')).encode())
print(json.dumps({'status':p['status'],'module_pin_entries':len(files),'proposal_sha256':sha(D/'m1-codex-campaign-proposal-v10.json')}))
