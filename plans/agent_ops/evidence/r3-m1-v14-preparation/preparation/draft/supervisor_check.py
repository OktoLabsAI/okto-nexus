"""Read only the exact proposed Connector service/task owner; no launch or stop."""
from pathlib import Path
from campaign_context import require

def observe_connector(context):
    from okto_nexus_connector.daemon import manager
    from okto_nexus_connector.daemon.lock import InstanceLock
    from okto_nexus_connector.platform.user_service import UserService,SUPERVISOR
    root=Path(context.P['paths']['connector_state']).resolve()
    require(root.is_relative_to(context.ROOT.resolve()),'CONNECTOR_HOME_OUTSIDE_CAMPAIGN')
    expected=context.C['tasks']['connector']
    service=UserService(root)
    require(service.name==expected['name'] and service.instance_id==expected['instance_id'],'CONNECTOR_TASK_IDENTITY_MISMATCH')
    receipt,task=service.observe()  # ownership, task digest, and launch context checks
    require(receipt is not None and task is not None and task.enabled and task.active,'OWNED_CONNECTOR_TASK_NOT_ACTIVE')
    state=manager.status(root,timeout=.5)
    require(state.state=='ready' and state.ipc_ok and state.running and not state.draining
        and state.supervisor==SUPERVISOR and state.instance_id==expected['instance_id']
        and bool(state.generation),'CONNECTOR_SUPERVISOR_NOT_READY')
    owner=InstanceLock(root/'run').live_owner()  # validates live PID and birth token
    require(owner is not None and owner.pid==state.pid and owner.generation==state.generation
        and owner.instance_id==state.instance_id and bool(owner.birth_token),'CONNECTOR_PROCESS_IDENTITY_UNCONFIRMED')
    return {'task_name':service.name,'task_digest':task.digest,'instance_id':state.instance_id,
        'state':state.state,'supervisor':state.supervisor,'pid':owner.pid,'birth_token':owner.birth_token,
        'generation':state.generation,'task_enabled':task.enabled,'task_active':task.active}

def require_work_owner(context):
    import json
    gate=json.loads((context.PUBLIC/'remote-supervisor-checked.json').read_text())
    require(gate.get('proposal_sha256')==context.args.expected_proposal_sha256
        and gate.get('ready_for_work') is True,'REMOTE_POSTCHECK_REQUIRED')
    current=observe_connector(context)
    require(current==gate['after'],'CONNECTOR_OWNER_CHANGED_AFTER_SETUP')
    return current
