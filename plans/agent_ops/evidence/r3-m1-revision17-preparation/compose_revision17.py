"""Compose the selected finite revision17; reuse qualified installation unchanged."""
from pathlib import Path
from copy import deepcopy
import ast,hashlib,json,sys
H=Path(__file__).resolve().parent;OLD=H.with_name('work-revision16');B=H.parent.parent
sys.path.insert(0,str(H))
from request_context import current_commands
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def pin(p):return {'path':str(Path(p).resolve()),'sha256':sha(p)}
def read(p):return json.loads(Path(p).read_bytes())
def save(p,v):Path(p).write_text(json.dumps(v,indent=2)+'\n',encoding='utf-8',newline='\n')
def literals(p):
    values={}
    for node in ast.parse(p.read_text(encoding='utf-8')).body:
        if isinstance(node,ast.Assign) and isinstance(node.targets[0],ast.Name) and node.targets[0].id in ('POLICY','ANCESTRY'):
            values[node.targets[0].id]=ast.literal_eval(node.value)
    return values
planpath=Path('C:/Users/jpamb/AppData/Local/Temp/m1-w17-technical-plan-pito7b7o/execution-plan.json')
assert sha(planpath)=='110c33923c99bbd0a2acd1f65ad042bb5e81fe790d11e629093aa8106b643f31'
plan=read(planpath);old=read(OLD/'amendment.json');installed=read(plan['package']['installation']['path'])
for item in [*plan['basis'].values(),plan['package']['installation'],plan['package']['runtime_freeze']]:assert sha(item['path'])==item['sha256']
assert not any((H/n).exists() for n in ('public','private','runtime-private','package'))
cp=plan['basis']['checkpoint'];companion=plan['basis']['closure_companion'];accounting=plan['basis']['accounting']
closure=read(companion['path']);usage=read(accounting['path'])
assert closure['original_checkpoint_and_closure_untouched'] and closure['decision_receipts']['final_receipt_completion_asserted'] is False
assert usage['cumulative_observed_tokens']==460793 and usage['charged_reservations']==14
proof={'status':'CLOSED_REVISION16_CANONICAL_SUCCESS_USEFUL_FALSE','root':str(OLD),
 'files':{'checkpoint':cp,'companion':companion,'accounting':accounting,'freeze':pin(OLD/'runtime-freeze.json'),
 'amendment':pin(OLD/'amendment.json'),'final_presence':plan['basis']['final_presence'],'closure':plan['basis']['closure'],
 'physical_exit':pin(OLD/'public/nexus-exit-proof.json'),'cleanup_proof':pin(OLD/'public/cleanup-nexus.json'),
 'uninstall':pin(OLD/'public/lifecycle-nexus-uninstall-result.json')},
 'old_conditional15_selected':False,'old_conditional15_eligible':False,'refund':False,
 'productive_turn_stage':'SUCCEEDED','useful_result_confirmed':False,
 'native_decision_receipt_stage_historical_snapshot':'SUBMITTED','receipt_completion_asserted':False}
save(H/'technical-predecessor.json',proof)
grants=deepcopy(old['expected_historical_grants']);assert len(grants)==6
selected=[g for g in grants if g['grant_id']=='grant_492ad6ea66f54663948cbd7438d1bcd8'];assert len(selected)==1
selected[0]['minimum_used_executions']=2
save(H/'historical-grants.json',{'grants':grants,'predecessor_review':pin(OLD/'public/authorize-local-review.json'),
 'minimum_used_basis':'Two canonical session openings already charged on the same existing grant; current state/counts must be reviewed. No duplicate grant appended.',
 'predecessor_accounting':accounting,'grant_plan':plan['grant_plan']})
legacy=literals(H/'modules/legacy_controller.py');assert legacy['POLICY']==plan['policy']
sources={key:pin(H/Path(v['path']).relative_to(OLD)) for key,v in old['sources'].items() if key!='upgrade'}
proposal=read(old['original']['proposal']);save(H/'commands.json',current_commands(read(proposal['execution_bundle']['commands']['path']),installed['python']))
value=deepcopy(old)
value.pop('migration',None)
value.update(format='okto.m1.v17.work-revision17',work_root=str(H),execution_plan=pin(planpath),
 execution_status='OFFLINE_PREPARATION_ROOT_REVIEW_REQUIRED',sources=sources,commands=pin(H/'commands.json'),
 installation=plan['package']['installation'],wheels=installed['wheels'],installed_probe=pin(OLD/'probe-qualification.json'),
 reused_package={'python_prefix':installed['python_prefix'],'qualification':pin(OLD/'qualification.json'),'freeze':plan['package']['runtime_freeze'],
                 'rebuild':False,'pip_run':False,'new_probe_or_native_tests':False},
 reused_service_context=pin(B/'campaign/nexus-home/service-context.json'),
 technical_predecessor=pin(H/'technical-predecessor.json'),native_decision_path=str(H/'private/native-decision.json'),
 policy=plan['policy'],controller_ancestry=legacy['ANCESTRY'],prompt_revision=plan['prompt_revision'],grant_plan=plan['grant_plan'],
 request_ids={'useful':plan['request_ids']['local_useful'],'continuation':plan['request_ids']['local_continuation'],
              'remote_useful':plan['request_ids']['remote_useful'],'remote_continuation':plan['request_ids']['remote_continuation']},
 remote_execution_enabled=False,remote_DX40='PENDING_SELECTORS_HELD_SEPARATE_QUALIFICATION',
 initial_minimum_observed_tokens=460793,initial_cumulative_reservations=14,remaining_tolerance_tokens=239207,
 scope='Local useful15/new session then continuation16 only after useful success in same session. Remote17/18 selectors held; no migration.',
 expected_historical_grants=grants,initial_work_checkpoint=plan['basis']['terminal_work_checkpoint'],
 predecessor_session_id='ses_7d4fc7d6c37508b2d0a6b479458da531',predecessor_connection_generation=9,
 predecessor_productive_stage='SUCCEEDED',predecessor_control_receipt_stage='SUBMITTED_HISTORICAL_SNAPSHOT',
 observation_bounds={'snapshot_seconds':1,'initialization_seconds':2,'poll_seconds':19,'freshness_seconds':20,
                     'cadence_seconds':24,'target_start_seconds':.2,'max_observed_requests':8},readiness_timeout_seconds=5)
assert value['reused_service_context']['sha256']=='c28a8d687a9415ac65f750586d18270754031edb9ea5ba094b1c65c554f38484'
assert sha(plan['prompt_revision']['data_input']['path'])==plan['prompt_revision']['data_input']['sha256']
assert not (B/'campaign/deliverables/local/report.json').exists()
value['input_fixture_pin']=plan['prompt_revision']['data_input']
value['basis']={**old['basis'],'checkpoint':cp,'companion':companion,'accounting':accounting,
 'historical_grants':pin(H/'historical-grants.json'),'technical_predecessor':pin(H/'technical-predecessor.json'),
 'execution_plan':pin(planpath),'predecessor_controller_freeze':pin(OLD/'runtime-freeze.json'),
 'predecessor_closure':plan['basis']['closure'],'command_failure_diagnosis':plan['basis']['command_failure_diagnosis'],
 'path_diagnosis':plan['basis']['path_diagnosis'],'historical_controller_freeze':old['basis']['controller_freeze'],
 'controller_freeze':pin(H/'controller-qualification/runtime-freeze.json')}
value['bundle_overrides']={key:pin(H/Path(v['path']).relative_to(OLD)) for key,v in old['bundle_overrides'].items() if key!='root_driver_upgrade_environment'}
value['technical_supersession']={'predecessor_amendment':pin(OLD/'amendment.json'),'predecessor_freeze':pin(OLD/'runtime-freeze.json'),
 'package_reused_unchanged':True,'migration_actions':0,'reservation_refunded':False,'historical_stream_settlement_synthesized':False,
 'technical_cap_change':{'from':17,'to':18,'preventive_from':500000,'preventive_to':600000,'standing_authorized_tokens':700000,'new_user_hash_approval_claimed':False},
 'predecessor_uncertainty':'Request14 canonical SUCCEEDED but report absent/useful false; first native decision recovery SUBMITTED, no completion or replay inferred.',
 'qualification_reuse':'W16 installed50/probe60/package provenance reused by exact hashes; only context, grant/history, prompt and finite controller deltas newly qualified.'}
save(H/'amendment.json',value)
print(json.dumps({'amendment_sha256':sha(H/'amendment.json'),'sources':len(sources),'policy':value['policy']}))
