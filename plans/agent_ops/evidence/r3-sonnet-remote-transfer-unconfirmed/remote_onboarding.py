"""Canonical Connector draft/operator review and one protected key transfer.

No effect on import; phase2 selection/pins are supplied by remote_context.
"""
from pathlib import Path
import importlib.util
import json
import subprocess
import time

from request_context import require, read_json, sha, pin, reserve


def bases(X):
    py=[X.python,'-I','-B','-X','utf8','-m']
    connector=py+['okto_nexus_connector.cli.main','--state-dir',X.P['paths']['connector_state']]
    nexus=py+['okto_nexus.adapters.inbound.cli.main']
    return connector,nexus


def draft_commands(X):
    connector,nexus=bases(X);p=X.P
    draft=X.PUBLIC/'sonnet-connector-draft.json'
    discover=connector+['--json','discover','--harness','claude_stream']
    create=connector+['connect','--server',p['origin'],'--harness','claude_stream',
        '--executable',p['native']['path'],'--project',p['paths']['project'],
        '--provider-home',p['provider_home'],'--binding-alias',p['profile'],
        '--request-id',p['setup_request_id'],'--setup-draft',str(draft),
        '--customize','--no-start-at-login']
    plan=nexus+['connect','--operator-profile',p['operator_profile'],'--remote-draft',str(draft),
        '--profile',p['profile'],'--new-agent',p['agent_id'],'--plan','--json','--home',p['paths']['operator_home']]
    # Ordered installed preferences: model,effort,permission,MCP,session,tool,minutes,actions,save.
    return discover,create,plan,'sonnet\n1\n2\n3\n2\n1\n60\n3\n1\n'


def invoke(X,name,argv,*,stdin=None,as_json=True,connector=False):
    require(name in ('discover','draft','plan'),'FINITE_ONBOARDING_SELECTION_REQUIRED')
    X.require_ready()
    reserve(X.PUBLIC/f'sonnet-{name}-reserved.json',{'state':'RESERVED_BEFORE_DISPATCH',
        'amendment_sha256':X.amendment_sha256,'argv':argv,'model_admissions':0})
    with (X.PRIVATE/f'sonnet-{name}.stdout').open('xb') as out, (X.PRIVATE/f'sonnet-{name}.stderr').open('xb') as err:
        child=subprocess.Popen(argv,cwd=X.ROOT,env=X.connector_env() if connector else X.base.env(),
            stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,stdout=out,stderr=err,
            creationflags=subprocess.CREATE_NO_WINDOW)
        # No timeout-kill or silent replay; outer root retains this one-shot process.
        child.communicate(None if stdin is None else stdin.encode('utf-8'))
    X.save(f'sonnet-{name}-returned.json',{'returncode':child.returncode,
        'stdout_sha256':sha(X.PRIVATE/f'sonnet-{name}.stdout'),'stderr_sha256':sha(X.PRIVATE/f'sonnet-{name}.stderr'),
        'model_admissions':0})
    require(child.returncode==0,'ONBOARDING_CLI_UNCONFIRMED_'+name)
    X.require_ready()
    return read_json(X.PRIVATE/f'sonnet-{name}.stdout') if as_json else None


def validate_inventory(value,selected):
    items=[row for row in value['candidates'] if row.get('adapter_id')=='claude_stream'
        and Path(row.get('launch_script') or row['executable']).resolve()==Path(selected['path']).resolve()]
    require(len(items)==1,'UNIQUE_INVENTORIED_CLAUDE_REQUIRED')
    row=items[0]
    require(row.get('launch_script') is None and row.get('fingerprint')=='sha256:'+selected['sha256'],
        'INVENTORIED_NATIVE_BYTES_CHANGED')
    return {k:row.get(k) for k in ('adapter_id','executable','fingerprint','version','build_identity','source')}


def validate_draft(document,p):
    require(document.get('format')=='okto.remote-setup-draft' and document.get('version')==1
        and document.get('setup_run_id')==p['setup_request_id'] and document.get('server_origin')==p['origin'],
        'DRAFT_IDENTITY_CHANGED')
    require(document['installation']['adapter_id']=='claude_stream'
        and isinstance(document['installation'].get('candidate_ref'),str)
        and document['start_at_login'] is False,'DRAFT_INSTALLATION_CHANGED')
    config=document['configuration']
    require(config['harness_settings']=={'model':'sonnet','permission_mode':'default','inherit_global_mcps':'disabled'},
        'REVIEWED_HARNESS_SETTINGS_CHANGED')
    require(config['session_policy']=='per_sender' and config['tool_access']=='ask'
        and config['authorization']=={'minutes':60,'actions':3,'no_expiry':False,'unlimited_actions':False},
        'REVIEWED_POLICY_CHANGED')
    require(config['alias']==p['profile'] and config['runtime_enabled'] is True,'DRAFT_PROFILE_CHANGED')
    return True


def draft(X):
    require(not (X.PUBLIC/'sonnet-connector-draft.json').exists(),'DRAFT_ALREADY_EXISTS')
    pin(X.P['native'])
    discover,create,_,answers=draft_commands(X)
    inventory=invoke(X,'discover',discover,connector=True)
    observed=validate_inventory(inventory,X.P['native'])
    X.save('sonnet-inventory-selection.json',observed)
    invoke(X,'draft',create,stdin=answers,as_json=False,connector=True)
    doc=read_json(X.PUBLIC/'sonnet-connector-draft.json')
    validate_draft(doc,X.P)
    # Canonical local record, not a hand-written configuration/profile.
    X.save('sonnet-draft-validated.json',{'draft_sha256':sha(X.PUBLIC/'sonnet-connector-draft.json'),
        'candidate_ref':doc['installation']['candidate_ref'],'configuration':doc['configuration'],
        'local_paths_supplied_explicitly':True,'provider_home_reference':X.P['provider_home'],
        'model_admissions':0})


def plan(X):
    draft=read_json(X.PUBLIC/'sonnet-connector-draft.json');validate_draft(draft,X.P)
    prior=read_json(X.PUBLIC/'sonnet-draft-validated.json')
    require(prior['draft_sha256']==sha(X.PUBLIC/'sonnet-connector-draft.json'),'DRAFT_CHANGED')
    _,_,argv,_=draft_commands(X)
    require(not X.profile_path.exists(),'NEW_REMOTE_PROFILE_REQUIRED')
    invoke(X,'plan',argv)
    doc=read_json(X.profile_path)
    require(doc['kind']=='remote_project_setup' and doc['state']=='review'
        and doc['server_id']==X.P['server_id'] and doc['remote_review']['draft']==draft
        and doc['review_revision']==doc['remote_review']['review_revision'],'CANONICAL_REMOTE_REVIEW_UNCONFIRMED')
    X.save('sonnet-review.json',{'review_revision':doc['review_revision'],'server_id':doc['server_id'],
        'profile':X.P['profile'],'profile_sha256':sha(X.profile_path),'review':doc['remote_review'],
        'model_admissions':0,'selection_required':'Root exact technical review of this canonical document before one transfer.'})


def transfer(X):
    selection=read_json(X.PUBLIC/'sonnet-review-selection.json')
    reviewed=read_json(X.PUBLIC/'sonnet-review.json')
    require(selection=={'amendment_sha256':X.amendment_sha256,'review_revision':reviewed['review_revision'],
        'profile_sha256':reviewed['profile_sha256'],'server_id':X.P['server_id'],'profile':X.P['profile']},
        'EXACT_REMOTE_REVIEW_SELECTION_REQUIRED')
    require(sha(X.profile_path)==reviewed['profile_sha256'],'REVIEW_PROFILE_CHANGED')
    X.require_connector_ready()
    connector,nexus=bases(X)
    handoff=X.PUBLIC/'sonnet-host-handoff.json'
    require(not handoff.exists(),'TRANSFER_HANDOFF_ALREADY_EXISTS')
    producer=nexus+['connect','--operator-profile',X.P['operator_profile'],'--profile',X.P['profile'],
        '--approve',reviewed['review_revision'],'--setup-receipt-output',str(handoff),
        '--no-chat','--timeout','110','--home',X.P['paths']['operator_home']]
    consumer=connector+['connect','--setup-receipt',str(handoff),'--alias',X.P['profile'],
        '--credential-stdin','--no-start-at-login']
    helper=pin(X.P['protected_transfer'])
    spec=importlib.util.spec_from_file_location('sonnet_protected_transfer',helper)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    reserve(X.PUBLIC/'sonnet-transfer-reserved.json',{'state':'RESERVED_BEFORE_DISPATCH',
        'amendment_sha256':X.amendment_sha256,'review_revision':reviewed['review_revision'],'model_admissions':0})
    deadline=time.monotonic()+120
    def guard(phase):
        require(phase in ('producer','consumer') and time.monotonic()<deadline,'TRANSFER_PHASE_EXPIRED')
        X.require_ready();X.require_connector_ready()
        return True
    env=X.connector_env();env['OKTO_NEXUS_CONNECTER_DAEMON_FG']='1'
    value=mod.transfer_once(producer_argv=producer,consumer_argv=consumer,env=X.base.env(),consumer_env=env,
        cwd=X.ROOT,timeout_seconds=120,synthetic_probe=False,
        consumer_ready_marker='Host handoff (contains no key): '+str(handoff),effect_guard=guard,deadline_monotonic=deadline)
    # Explicit allowlist only; never key/password/terminal byte streams.
    public={k:value.get(k) for k in ('status','producer_exit','consumer_exit','active_job_processes_after',
        'forced_owned_cleanup','effect_guard_required','effect_gates_allowed','public_ipc_readers_joined')}
    X.save('sonnet-transfer-result.json',public)
    require(public['status']=='TRANSFERRED_ONCE' and public['producer_exit']==0 and public['consumer_exit']==0
        and public['active_job_processes_after']==0 and public['forced_owned_cleanup'] is False
        and public['effect_guard_required'] is True and public['effect_gates_allowed']==['producer','consumer']
        and public['public_ipc_readers_joined'] is True,'PROTECTED_TRANSFER_UNCONFIRMED_NO_REPLAY')
    doc=read_json(X.profile_path)
    require(doc['state']=='done' and doc['server_id']==X.P['server_id'],'REMOTE_PROFILE_NOT_DONE')
    X.require_ready();X.require_connector_ready()
    X.save('sonnet-profile-completed.json',{'profile_sha256':sha(X.profile_path),'profile':X.P['profile'],
        'server_id':doc['server_id'],'remote_scope':doc['remote_scope'],'model_admissions':0})
