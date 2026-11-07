"""One canonical remote bootstrap/key transfer; no productive turn or replay."""
from pathlib import Path
import importlib.util,json,sys,time
sys.path.insert(0,str(Path(__file__).parent))
from campaign_context import load,require,reserve_json
X=load()
P,C,ROOT=X.P,X.C,X.ROOT
require(X.remaining==['transfer'],'REMOTE_SELECTION_INVALID')
from supervisor_check import observe_connector
profile=P['execution_bundle']['profiles']['connector']
operator=P['execution_bundle']['operator_profile']
operator_home=Path(P['paths']['operator_home'])
profile_file=operator_home/'terminal/profiles'/(profile+'.json')
document=json.loads(profile_file.read_text())
require(document.get('kind')=='remote_project_setup' and document.get('state')=='review','FRESH_REMOTE_REVIEW_REQUIRED')
review=document['remote_review'];draft=review['draft']
require(document['review_revision']==review['review_revision'],'REMOTE_REVISION_MISMATCH')
require(draft['server_origin']==C['origin'] and draft['setup_run_id']=='m1v8-connector-setup'
    and draft['installation']['candidate_ref']==P['native_selection']['candidate_ref']
    and draft['start_at_login'] is False,'REMOTE_DRAFT_SCOPE_MISMATCH')
# This explicit operator selection is made from the current canonical plan by
# the agent before this script; it contains no key and grants no broad prefix.
selected=json.loads((ROOT/'public/remote-review-selection.json').read_text())
require(selected.get('proposal_sha256')==X.args.expected_proposal_sha256
    and selected.get('review_revision')==document['review_revision']
    and selected.get('server_id')==document['server_id']
    and selected.get('profile')==profile,'REMOTE_REVIEW_SELECTION_REQUIRED')
handoff=ROOT/'public/remote-host-handoff.json'
require(not handoff.exists(),'REMOTE_HANDOFF_ALREADY_EXISTS')
controller=X.controller()
try:
    summary=controller.summary()
    require(summary['can_admit'] and not summary['current'],'CAMPAIGN_NOT_QUIESCENT_FOR_REMOTE_SETUP')
    before=observe_connector(X)
    # Never replay a transfer: bootstrap/material delivery can be irreversible
    # even if the helper or its public receipt later reports uncertainty.
    reservation=ROOT/'public/remote-pty-reservation.json'
    reserve_json(reservation,{'state':'DISPATCH_RESERVED','time':time.time(),
        'proposal_sha256':X.args.expected_proposal_sha256,'review_revision':document['review_revision'],
        'before':before,'ensure_start_calls_maximum':1,
        'implicit_scheduler_start_maximum':1,'productive_model_turns':0})
    base=[P['package_pins']['python'],'-I','-B','-m','okto_nexus.adapters.inbound.cli.main']
    producer=base+['connect','--operator-profile',operator,'--profile',profile,
        '--approve',document['review_revision'],'--setup-receipt-output',str(handoff),
        '--no-chat','--timeout','110','--home',str(operator_home)]
    consumer=[P['package_pins']['python'],'-I','-B','-m','okto_nexus_connector.cli.main',
        '--state-dir',P['paths']['connector_state'],'connect',
        '--setup-receipt',str(handoff),'--alias',profile,'--credential-stdin','--no-start-at-login']
    consumer_env=X.env()
    consumer_env['OKTO_NEXUS_CONNECTER_DAEMON_FG']='1'  # this consumer only
    helper=Path(P['execution_bundle']['files']['protected_pty']['path'])
    sys.path.insert(0,str(helper.parent))  # preserve original helper/venv origin
    spec=importlib.util.spec_from_file_location('protected_pty',helper)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    result=module.transfer_once(producer_argv=producer,consumer_argv=consumer,
        env=X.env(),consumer_env=consumer_env,cwd=ROOT,timeout_seconds=120,synthetic_probe=False,
        consumer_ready_marker='Host handoff (contains no key): '+str(handoff))
    reserve_json(ROOT/'public/remote-pty-result.json',dict(result,proposal_sha256=X.args.expected_proposal_sha256))
    require(result.get('status')=='TRANSFERRED_ONCE' and result.get('producer_exit')==0
        and result.get('consumer_exit')==0 and result.get('active_job_processes_after')==0
        and not result.get('forced_owned_cleanup'),'REMOTE_TRANSFER_UNCONFIRMED')
    after=observe_connector(X)
    require(after['instance_id']==before['instance_id'] and after['task_name']==before['task_name']
        and after['task_digest']==before['task_digest'],'REMOTE_TASK_CHANGED')
    child_pids={result.get(key,{}).get('pid') for key in ('producer','consumer')}
    child_pids.add(result.get('worker_pid'))
    require(after['pid'] not in child_pids,'SERVICE_INSIDE_AUXILIARY_JOB')
    final=json.loads(profile_file.read_text())
    require(final.get('state')=='done' and final.get('server_id')==document['server_id'],'REMOTE_FINISH_NOT_CONFIRMED')
    reserve_json(ROOT/'public/remote-supervisor-checked.json',{'proposal_sha256':X.args.expected_proposal_sha256,
        'before':before,'after':after,'generation_changed':before['generation']!=after['generation'],
        'ensure_start_calls_maximum':1,'implicit_scheduler_start_maximum':1,
        'preflight_is_atomic_fence':False,'ready_for_work':True,'finish_state':'done'})
    print(json.dumps({'status':'REMOTE_FINISH_AND_OWNER_CONFIRMED','generation_changed':before['generation']!=after['generation'],
        'key_material_public':False,'productive_model_turns':0}),flush=True)
except BaseException as error:
    controller.fault('REMOTE_SETUP_UNCONFIRMED')
    print(json.dumps({'status':'REMOTE_SETUP_UNCONFIRMED','error_type':type(error).__name__,
        'replay_allowed':False,'new_work_allowed':False}),flush=True)
    raise SystemExit(3) from None
finally:
    controller.close()
