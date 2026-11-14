"""Offline explicit revision15 composition; no service/provider/credential operations."""
from pathlib import Path
from copy import deepcopy
import ast,hashlib,json,sys
H=Path(__file__).resolve().parent;OLD=H.with_name('work-request12-package2');B=H.parent.parent
sys.path.insert(0,str(H))
from request_context import current_commands
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def pin(p):return {'path':str(Path(p).resolve()),'sha256':sha(p)}
def read(p):return json.loads(Path(p).read_bytes())
def save(p,v):Path(p).write_text(json.dumps(v,indent=2)+'\n',encoding='utf-8')
def revision(v):return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
def literals(p):
    values={}
    for node in ast.parse(p.read_text(encoding='utf-8')).body:
        if isinstance(node,ast.Assign) and isinstance(node.targets[0],ast.Name) and node.targets[0].id in ('POLICY','ANCESTRY'):
            values[node.targets[0].id]=ast.literal_eval(node.value)
    return values
plan_path=Path('C:/Users/jpamb/AppData/Local/Temp/m1-next-work-plan-83_ksszr/execution-plan.json')
plan=read(plan_path);assert sha(plan_path)=='7af863dd3176df050ffcdfd9cd44f75adbf4314274e77c2cdf7fdf6f035c040a'
old=read(OLD/'amendment.json');installed=read(H/'package/installation.json')
assert read(H/'probe-qualification.json')['status']=='CANONICAL_PROBE60_PASS'
assert not (H/'public').exists() and not (H/'private').exists()
cp=OLD/'private/controller.json';assert sha(cp)=='70826adc11d41aba2ed84b56e8b673e0f8153d5a550c1d34ec7abfce515c5c37'
companion=plan['basis']['closure'];accounting=plan['basis']['accounting']
assert sha(companion['path'])==companion['sha256'] and sha(accounting['path'])==accounting['sha256']
closure=read(companion['path']);usage=read(accounting['path'])
assert closure['original_checkpoint_untouched'] and closure['interrupt']['receipt_stage']=='SUBMITTED'
assert usage['cumulative_observed_tokens']==295262 and usage['charged_reservations']==12
proof={'status':'CLOSED_PACKAGE2_WITH_CONTROL_RECEIPT_UNCONFIRMED','root':str(OLD),
 'files':{'checkpoint':pin(cp),'companion':companion,'accounting':accounting,
          'freeze':pin(OLD/'runtime-freeze.json'),'amendment':pin(OLD/'amendment.json'),
          'final_presence':pin(OLD/'public/final-presence.json')},
 'old_conditional13_selected':False,'old_conditional13_eligible':False,'refund':False,
 'productive_turn_stage':'CANCELLED','control_receipt_stage':'SUBMITTED','control_receipt_completion_asserted':False}
save(H/'technical-predecessor.json',proof)
grant_history=deepcopy(old['expected_historical_grants'])
applied=read(OLD/'public/authorize-local-apply.json')
grant_history.append({**{k:applied['grant'][k] for k in ('grant_id','expires_at','max_executions')},'revision':1,'minimum_used_executions':1})
save(H/'historical-grants.json',{'grants':grant_history,'new_grant_source':pin(OLD/'public/authorize-local-apply.json'),
 'minimum_used_basis':'One canonical opening for request12 observed; current actual usage/state must be reviewed before any grant selection.'})
legacy=literals(H/'modules/legacy_controller.py');assert legacy['POLICY']==plan['policy']
sources={key:pin(H/Path(entry['path']).relative_to(OLD)) for key,entry in old['sources'].items()}
proposal=read(old['original']['proposal']);commands=current_commands(read(proposal['execution_bundle']['commands']['path']),installed['python'])
save(H/'commands.json',commands)
value=deepcopy(old)
value.update(format='okto.m1.v15.work-revision15',work_root=str(H),execution_plan=pin(plan_path),
    execution_status='OFFLINE_PREPARATION_ROOT_REVIEW_REQUIRED',sources=sources,commands=pin(H/'commands.json'),
    installation=pin(H/'package/installation.json'),wheels=installed['wheels'],
    technical_predecessor=pin(H/'technical-predecessor.json'),installed_probe=pin(H/'probe-qualification.json'),
    native_decision_path=str(H/'private/native-decision.json'),policy=plan['policy'],controller_ancestry=legacy['ANCESTRY'],
    request_ids={'useful':plan['request_ids']['local_useful'],'continuation':plan['request_ids']['local_continuation'],
                 'remote_useful':plan['request_ids']['remote_useful'],'remote_continuation':plan['request_ids']['remote_continuation']},
    remote_execution_enabled=False,remote_DX40='PENDING_SELECTORS_HELD_SEPARATE_QUALIFICATION',
    initial_minimum_observed_tokens=295262,initial_cumulative_reservations=12,remaining_tolerance_tokens=404738,
    scope='Local useful13/new session then same-session continuation14 after success. Remote15/16 IDs allocated but selectors closed.',
    expected_historical_grants=grant_history,
    initial_work_checkpoint=pin(B/'campaign/nexus-home/terminal/work/m1v12-local.json'),
    predecessor_session_id='ses_7c8b77c2988e1645a0c9b6aefd6d80bc',predecessor_connection_generation=7,
    predecessor_productive_stage='CANCELLED',predecessor_control_receipt_stage='SUBMITTED',
    observation_bounds={'snapshot_seconds':1,'initialization_seconds':2,'poll_seconds':17,'freshness_seconds':18,
                        'cadence_seconds':22,'target_start_seconds':.2,'max_observed_requests':7},
    readiness_timeout_seconds=5)
fixture=B/'campaign/local-project/numbers.csv'
assert sha(fixture)=='876c1313400238ba1b78cc54fab94411c28b74d2c592c69422eb89800f634d4b'
assert not (B/'campaign/deliverables/local/report.json').exists()
value['input_fixture_pin']=pin(fixture)
value['basis']={**old['basis'],'checkpoint':pin(cp),'companion':companion,'accounting':accounting,
               'historical_grants':pin(H/'historical-grants.json'),'technical_predecessor':pin(H/'technical-predecessor.json'),
               'execution_plan':pin(plan_path),'predecessor_controller_freeze':pin(OLD/'runtime-freeze.json')}
value['basis']['historical_controller_freeze']=old['basis']['controller_freeze']
value['basis']['controller_freeze']=pin(H/'controller-qualification/runtime-freeze.json')
value['bundle_overrides']={key:pin(H/Path(entry['path']).relative_to(OLD)) for key,entry in old['bundle_overrides'].items()}
home=B/'campaign/nexus-home';run=read(home/'service-run.json');shutdown=read(home/'service-shutdown.json')
assert run['state']=='drained' and shutdown['state']=='DRAINED' and run['generation']==shutdown['generation']=='3f322a5e7874bdca13a6c4d2cd4f6435'
value['migration']={'run':pin(home/'service-run.json'),'shutdown':pin(home/'service-shutdown.json'),
 'source_context':pin(home/'service-context.json'),'source_context_revision':revision(read(home/'service-context.json')),
 'generation':run['generation'],'target_python':installed['python'],'source_drain_observed':True,
 'scope':'New canonical upgrade-plan and exact reviewed apply from context schema revision2, with current absent owner/task. No start or model.'}
value['technical_supersession']={'predecessor_amendment':pin(OLD/'amendment.json'),'predecessor_freeze':pin(OLD/'runtime-freeze.json'),
 'source_commits':read(H/'package/build-provenance.json')['sources'],'new_candidate_requires_new_upgrade_plan':True,
 'old_plan_reused':False,'reservation_refunded':False,'historical_stream_settlement_synthesized':False,
 'technical_cap_change':{'from':13,'to':16,'standing_authorized_tokens':700000,'new_user_hash_approval_claimed':False},
 'predecessor_uncertainty':'Request12 target CANCELLED but interrupt receipt SUBMITTED; original checkpoint/faults retained, no replay.',
 'qualification_reuse':'Unchanged lifecycle/upgrade semantics retain prior qualification; revision15 explicit paths/policy/history/limits/CLI preflight deltas qualify separately.'}
value['normal_fault_containment']={'selected_only_on_faulted_admitted_native_turn':True,'force_authorized':False,
 'trigger':'Normal stop45 remains draining with exact active native turn',
 'required_fresh_scope':['owner generation and all three process births/cycle','canonical session and productive operation','native turn and pending request metadata'],
 'allowed_action':'One canonical intents:resolve plus one operations admission for turn.interrupt, using a fresh unique cleanup client intent and durable one-shot ledger; no native approve/deny replay, no new provider turn.',
 'sequence':'Root reviews concrete current identities/argv, selects normal interrupt, observes target terminal and usage, then canonical runtime.close (TerminalWork action close) only if necessary and normal stop separately; retain physical cohort and native inactivity proofs.',
 'reference_manifest':pin(Path('C:/Users/jpamb/AppData/Local/Temp/m1-request12-normal-containment-h4c6sw5t/manifest.json')),
 'reference_is_not_reexecutable_authority':True,'completion_receipt_not_inferred_from_target_exit':True}
save(H/'amendment.json',value)
print(json.dumps({'amendment_sha256':sha(H/'amendment.json'),'sources':len(sources),'policy':value['policy']}))
