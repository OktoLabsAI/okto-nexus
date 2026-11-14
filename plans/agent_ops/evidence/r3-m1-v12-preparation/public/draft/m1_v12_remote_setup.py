"""One canonical remote bootstrap/key transfer; no productive turn or replay."""
from pathlib import Path
import importlib.util,json,os,subprocess,sys,time
sys.path.insert(0,str(Path(__file__).parent))
from campaign_context import load,require,reserve_json
X=load()
P,C,ROOT=X.P,X.C,X.ROOT
require(X.remaining==['transfer'],'REMOTE_SELECTION_INVALID')
from supervisor_check import observe_connector
from publication import poll_and_publish
from remote_transfer_monitor import transfer_with_monitor,public_transfer_result
from remote_stop_order import DeferredRemoteStops
profile=P['execution_bundle']['profiles']['connector']
operator=P['execution_bundle']['operator_profile']
operator_home=Path(P['paths']['operator_home'])
profile_file=operator_home/'terminal/profiles'/(profile+'.json')
document=json.loads(profile_file.read_text())
require(document.get('kind')=='remote_project_setup' and document.get('state')=='review','FRESH_REMOTE_REVIEW_REQUIRED')
review=document['remote_review'];draft=review['draft']
require(document['review_revision']==review['review_revision'],'REMOTE_REVISION_MISMATCH')
require(draft['server_origin']==C['origin'] and draft['setup_run_id']=='m1v12-connector-setup'
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
sys.path.insert(0,str(X.modules))
from history_observers import attach_existing_work
stops=[];handles=[];publication_diagnostics={};stop_sequence=0
transfer_result=None;transfer_monitor=None

def publish(value):
    target=ROOT/'public/live-accounting.json';pending=target.with_suffix('.pending')
    with pending.open('w',encoding='utf-8') as stream:
        json.dump(value,stream,indent=2);stream.flush();os.fsync(stream.fileno())
    os.replace(pending,target)

def poll():
    summary=poll_and_publish(controller,publish,publication_diagnostics,None)
    if summary.get('can_admit') is not True:stop_order.select_both()
    return summary

def dispatch_stop(lane):
    component='nexus' if lane=='local' else 'connector'
    record=ROOT/'public'/f'lifecycle-{component}-stop.json'
    if record.exists():
        return {'action_record':record.name,'existing_reservation':True,'replayed':False}
    out=(ROOT/'private'/f'remote-{component}-stop-wrapper.stdout').open('xb')
    err=(ROOT/'private'/f'remote-{component}-stop-wrapper.stderr').open('xb');handles.extend((out,err))
    child=subprocess.Popen(X.stop_argv(component),cwd=ROOT,env=X.env(),stdout=out,stderr=err,
        creationflags=subprocess.CREATE_NO_WINDOW)
    stops.append(child)
    return {'wrapper_pid':child.pid,'action_record':record.name,'stop_confirmed':False}

def persist_stop_order(value):
    global stop_sequence
    stop_sequence+=1
    reserve_json(ROOT/'public'/f'remote-stop-order-{stop_sequence:04d}.json',dict(value,
        proposal_sha256=X.args.expected_proposal_sha256))

def existing_stop(lane):
    component='nexus' if lane=='local' else 'connector'
    return (ROOT/'public'/f'lifecycle-{component}-stop.json').exists()

stop_order=DeferredRemoteStops(persist=persist_stop_order,dispatch=dispatch_stop,existing_receipt=existing_stop)
stop_owner=stop_order.select

try:
    # Setup history can exist before any work. Its owner still needs the same
    # canonical stop callback if late setup usage or a phase fault is observed.
    controller.attach_owner('local',P['paths']['server_home'],lambda:stop_owner('local'))
    attached=attach_existing_work(controller,campaign_root=ROOT,server_home=P['paths']['server_home'],
        connector_state=P['paths']['connector_state'],stop_for_lane=stop_owner)
    summary=poll()
    require(summary['can_admit'] and not summary['current'],'CAMPAIGN_NOT_QUIESCENT_FOR_REMOTE_SETUP')
    before=observe_connector(X)
    stop_order.ready()
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
    def transfer(*,effect_guard,deadline_monotonic):
        return module.transfer_once(producer_argv=producer,consumer_argv=consumer,
            env=X.env(),consumer_env=consumer_env,cwd=ROOT,timeout_seconds=120,synthetic_probe=False,
            consumer_ready_marker='Host handoff (contains no key): '+str(handoff),
            effect_guard=effect_guard,deadline_monotonic=deadline_monotonic)
    # Conservative reservation on owner before the retained thread can invoke
    # the helper. Only the returned owned-Job proof can release normal stops.
    stop_order.helper_started()
    result,monitor=transfer_with_monitor(controller=controller,transfer=transfer,poll=poll,timeout_seconds=120)
    transfer_result,transfer_monitor=result,monitor
    stop_order.finish(result,monitor)
    reserve_json(ROOT/'public/remote-pty-result.json',dict(public_transfer_result(result),
        proposal_sha256=X.args.expected_proposal_sha256,monitor=monitor,
        historical_lanes_attached=attached,publication_diagnostics=publication_diagnostics,
        stop_order=stop_order.snapshot()))
    require(monitor['worker_joined'] and monitor['ordered_effect_gates_passed']
        and not monitor['fence_selected'],'REMOTE_TRANSFER_FENCE_CLOSED')
    require(result.get('status')=='TRANSFERRED_ONCE' and result.get('producer_exit')==0
        and result.get('consumer_exit')==0 and result.get('active_job_processes_after')==0
        and not result.get('forced_owned_cleanup') and result.get('effect_guard_required') is True
        and result.get('effect_gates_allowed')==['producer','consumer']
        and result.get('public_ipc_readers_joined') is True
        and stop_order.data['helper_drained'] is True,'REMOTE_TRANSFER_UNCONFIRMED')
    after=observe_connector(X)
    require(after['instance_id']==before['instance_id'] and after['task_name']==before['task_name']
        and after['task_digest']==before['task_digest'],'REMOTE_TASK_CHANGED')
    child_pids={result.get(key,{}).get('pid') for key in ('producer','consumer')}
    child_pids.add(result.get('worker_pid'))
    require(after['pid'] not in child_pids,'SERVICE_INSIDE_AUXILIARY_JOB')
    final=json.loads(profile_file.read_text())
    require(final.get('state')=='done' and final.get('server_id')==document['server_id'],'REMOTE_FINISH_NOT_CONFIRMED')
    summary=poll()
    require(summary.get('can_admit') is True and not summary.get('current'),'CAMPAIGN_BLOCKED_AFTER_REMOTE_FINISH')
    reserve_json(ROOT/'public/remote-supervisor-checked.json',{'proposal_sha256':X.args.expected_proposal_sha256,
        'before':before,'after':after,'generation_changed':before['generation']!=after['generation'],
        'ensure_start_calls_maximum':1,'implicit_scheduler_start_maximum':1,
        'preflight_is_atomic_fence':False,'ready_for_work':True,'finish_state':'done'})
    print(json.dumps({'status':'REMOTE_FINISH_AND_OWNER_CONFIRMED','generation_changed':before['generation']!=after['generation'],
        'key_material_public':False,'productive_model_turns':0}),flush=True)
except BaseException as error:
    fault_error_type=None
    try:controller.fault('REMOTE_SETUP_UNCONFIRMED')
    except BaseException as fault_error:fault_error_type=type(fault_error).__name__
    try:poll()
    except BaseException:pass
    # A Connector without work history still belongs to this verified remote
    # phase. Select both services, then reconcile the same one-shot receipts.
    try:
        stop_order.select_both()
        stop_order.finish(transfer_result,transfer_monitor)
        stop_order.dispatch_selected()
    except BaseException as stop_error:
        fault_error_type=fault_error_type or type(stop_error).__name__
    while any(child.poll() is None for child in stops):
        try:poll()
        except BaseException:pass
        time.sleep(.2)
    print(json.dumps({'status':'REMOTE_SETUP_UNCONFIRMED','error_type':type(error).__name__,
        'fault_persistence_error_type':fault_error_type,
        'stop_order':stop_order.snapshot(),
        'replay_allowed':False,'new_work_allowed':False}),flush=True)
    raise SystemExit(3) from None
finally:
    controller.close()
    for handle in handles:handle.close()
