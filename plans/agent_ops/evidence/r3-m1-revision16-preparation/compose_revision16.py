"""Offline explicit revision16 composition; no service/provider/credential operations."""
from pathlib import Path
from copy import deepcopy
import ast,hashlib,json,sys
H=Path(__file__).resolve().parent;OLD=H.with_name('work-revision15');B=H.parent.parent
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
plan_path=Path('C:/Users/jpamb/AppData/Local/Temp/m1-w16-selected-plan-a0xzgmki/execution-plan.json')
plan=read(plan_path);assert sha(plan_path)=='1c7a64e3257c8b3ee0020528a1c0bfe4f080c04f94d392d0066b8ca5b473ecea'
old=read(OLD/'amendment.json');installed=read(H/'package/installation.json')
assert read(H/'probe-qualification.json')['status']=='CANONICAL_PROBE60_PASS'
assert not (H/'public').exists() and not (H/'private').exists()
cp=OLD/'private/controller.json';assert sha(cp)=='05c09e7168f6251523e1d75a4c523792e12967a2ef0474264a8c754fe6eaf0d3'
companion=pin(Path('D:/Projetos/Techridy/okto_labs_okto_nexus/plans/agent_ops/evidence/r3-m1-revision15-execution/closure-companion.json'))
accounting=pin(Path('C:/Users/jpamb/AppData/Local/Temp/m1-v15-normal-interrupt-evdv8vdv/accounting-reconciliation.json'))
assert sha(companion['path'])==companion['sha256'] and sha(accounting['path'])==accounting['sha256']
closure=read(companion['path']);usage=read(accounting['path'])
assert closure['original_checkpoint_and_closure_untouched'] and closure['interrupt']['receipt_stage']=='SUBMITTED'
assert usage['cumulative_observed_tokens']==341276 and usage['charged_reservations']==13
proof={'status':'CLOSED_REVISION15_WITH_CONTROL_RECEIPT_UNCONFIRMED','root':str(OLD),
 'files':{'checkpoint':pin(cp),'companion':companion,'accounting':accounting,
          'freeze':pin(OLD/'runtime-freeze.json'),'amendment':pin(OLD/'amendment.json'),
          'final_presence':pin(OLD/'public/final-presence.json'),
          'closure':pin(OLD/'public/closure.json'),'physical_exit':pin(OLD/'public/nexus-exit-proof.json'),
          'cleanup_proof':pin(OLD/'public/cleanup-nexus.json'),'uninstall':pin(OLD/'public/lifecycle-nexus-uninstall-result.json')},
 'old_conditional14_selected':False,'old_conditional14_eligible':False,'refund':False,
 'productive_turn_stage':'CANCELLED','control_receipt_stage':'SUBMITTED','control_receipt_completion_asserted':False}
save(H/'technical-predecessor.json',proof)
grant_history=deepcopy(old['expected_historical_grants'])
applied=read(OLD/'public/authorize-local-apply.json')
grant_history.append({**{k:applied['grant'][k] for k in ('grant_id','expires_at','max_executions')},'revision':1,'minimum_used_executions':1})
save(H/'historical-grants.json',{'grants':grant_history,'new_grant_source':pin(OLD/'public/authorize-local-apply.json'),
 'minimum_used_basis':'One canonical opening for request13 observed; current actual usage/state must be reviewed before any grant selection.'})
legacy=literals(H/'modules/legacy_controller.py');assert legacy['POLICY']==plan['policy']
sources={key:pin(H/Path(entry['path']).relative_to(OLD)) for key,entry in old['sources'].items()}
proposal=read(old['original']['proposal']);commands=current_commands(read(proposal['execution_bundle']['commands']['path']),installed['python'])
save(H/'commands.json',commands)
value=deepcopy(old)
value.update(format='okto.m1.v16.work-revision16',work_root=str(H),execution_plan=pin(plan_path),
    execution_status='OFFLINE_PREPARATION_ROOT_REVIEW_REQUIRED',sources=sources,commands=pin(H/'commands.json'),
    installation=pin(H/'package/installation.json'),wheels=installed['wheels'],
    technical_predecessor=pin(H/'technical-predecessor.json'),installed_probe=pin(H/'probe-qualification.json'),
    native_decision_path=str(H/'private/native-decision.json'),policy=plan['policy'],controller_ancestry=legacy['ANCESTRY'],
    request_ids={'useful':plan['request_ids']['local_useful'],'continuation':plan['request_ids']['local_continuation'],
                 'remote_useful':plan['request_ids']['remote_useful'],'remote_continuation':plan['request_ids']['remote_continuation']},
    remote_execution_enabled=False,remote_DX40='PENDING_SELECTORS_HELD_SEPARATE_QUALIFICATION',
    initial_minimum_observed_tokens=341276,initial_cumulative_reservations=13,remaining_tolerance_tokens=358724,
    scope='Local useful14/new session then same-session continuation15 after success. Remote16/17 IDs allocated but selectors closed.',
    expected_historical_grants=grant_history,
    initial_work_checkpoint=pin(B/'campaign/nexus-home/terminal/work/m1v12-local.json'),
    predecessor_session_id='ses_86bf8a7f016fafe06e794ce5f0028611',predecessor_connection_generation=8,
    predecessor_productive_stage='CANCELLED',predecessor_control_receipt_stage='SUBMITTED',
    observation_bounds={'snapshot_seconds':1,'initialization_seconds':2,'poll_seconds':19,'freshness_seconds':20,
                        'cadence_seconds':24,'target_start_seconds':.2,'max_observed_requests':8},
    readiness_timeout_seconds=5)
fixture=B/'campaign/local-project/numbers.csv'
assert sha(fixture)=='876c1313400238ba1b78cc54fab94411c28b74d2c592c69422eb89800f634d4b'
assert not (B/'campaign/deliverables/local/report.json').exists()
value['input_fixture_pin']=pin(fixture)
value['basis']={**old['basis'],'checkpoint':pin(cp),'companion':companion,'accounting':accounting,
               'historical_grants':pin(H/'historical-grants.json'),'technical_predecessor':pin(H/'technical-predecessor.json'),
               'execution_plan':pin(plan_path),'predecessor_controller_freeze':pin(OLD/'runtime-freeze.json'),
               'predecessor_closure':plan['basis']['closure'],'native_refusal_diagnosis':plan['basis']['native_refusal_diagnosis']}
value['basis']['historical_controller_freeze']=old['basis']['controller_freeze']
value['basis']['controller_freeze']=pin(H/'controller-qualification/runtime-freeze.json')
value['bundle_overrides']={key:pin(H/Path(entry['path']).relative_to(OLD)) for key,entry in old['bundle_overrides'].items()}
home=B/'campaign/nexus-home';run=read(home/'service-run.json');shutdown=read(home/'service-shutdown.json')
assert run['state']=='drained' and shutdown['state']=='DRAINED' and run['generation']==shutdown['generation']=='000516de38262af8bdf99dee1c5271bc'
value['migration']={'run':pin(home/'service-run.json'),'shutdown':pin(home/'service-shutdown.json'),
 'source_context':pin(home/'service-context.json'),'source_context_revision':revision(read(home/'service-context.json')),
 'generation':run['generation'],'target_python':installed['python'],'source_drain_observed':True,
 'scope':'New canonical upgrade-plan and exact reviewed apply from context schema revision2, with current absent owner/task. No start or model.'}
value['technical_supersession']={'predecessor_amendment':pin(OLD/'amendment.json'),'predecessor_freeze':pin(OLD/'runtime-freeze.json'),
 'source_commits':read(H/'package/build-provenance.json')['sources'],'new_candidate_requires_new_upgrade_plan':True,
 'old_plan_reused':False,'reservation_refunded':False,'historical_stream_settlement_synthesized':False,
 'technical_cap_change':{'from':16,'to':17,'standing_authorized_tokens':700000,'new_user_hash_approval_claimed':False},
 'predecessor_uncertainty':'Request13 target CANCELLED but interrupt receipt SUBMITTED; original checkpoint/faults retained, no replay.',
 'qualification_reuse':'Unchanged lifecycle/upgrade semantics retain prior qualification; revision16 explicit paths/policy/history/limits/CLI preflight deltas qualify separately.'}
value['normal_fault_containment']={'selected_only_on_faulted_admitted_native_turn':True,'force_authorized':False,
 'trigger':'Normal stop45 remains draining with exact active native turn',
 'required_fresh_scope':['owner generation and all three process births/cycle','canonical session and productive operation','native turn and pending request metadata'],
 'allowed_action':'One canonical intents:resolve plus one operations admission for turn.interrupt, using a fresh unique cleanup client intent and durable one-shot ledger; no native approve/deny replay, no new provider turn.',
 'sequence':'Root reviews concrete current identities/argv, selects normal interrupt, observes target terminal and usage, then canonical runtime.close (TerminalWork action close) only if necessary and normal stop separately; retain physical cohort and native inactivity proofs.',
 'reference_manifest':pin(Path('C:/Users/jpamb/AppData/Local/Temp/m1-v15-normal-interrupt-evdv8vdv/manifest.json')),
 'reference_is_not_reexecutable_authority':True,'completion_receipt_not_inferred_from_target_exit':True}
save(H/'amendment.json',value)
print(json.dumps({'amendment_sha256':sha(H/'amendment.json'),'sources':len(sources),'policy':value['policy']}))
