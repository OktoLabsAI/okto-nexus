"""Exact two-task absence after local-only cohort cleanup; no work settlement claim."""
from pathlib import Path
import json,socket,sys,time
sys.path.insert(0,str(Path(__file__).resolve().parent))
from driver_common import gate,parser,main_guard,require,read_json,require_tags,sha,public_save,invocation_inventory
from m1_v14_observation import endpoint,canonical_absence
from cohort import validate_exit

def check(context,task_reader,*,absence=canonical_absence):
    inventory=invocation_inventory(context)
    allowed={('lifecycle',('nexus',action)) for action in ('install','start','stop','uninstall')}
    allowed|={('authorize_local',(phase,)) for phase in ('review','apply')}
    allowed|={('work',('local',phase)) for phase in ('useful','continuation')}
    allowed|={('upgrade',(phase,)) for phase in ('plan','apply')}
    require(all((v['mode'],tuple(v['selection'])) in allowed and v.get('returned_sha256')
        for v in inventory.values()),'LOCAL_ONLY_COMPLETED_INVOCATIONS_REQUIRED')
    require(not any(p.name.startswith(('remote-','connector-','lifecycle-connector-'))
        for folder in (context.PUBLIC,context.PRIVATE) for p in folder.iterdir()),'REMOTE_EFFECT_EVIDENCE_PRESENT')
    basis=context.amendment['basis']['companion'];require(sha(basis['path'])==basis['sha256'],'PREDECESSOR_CHANGED')
    previous=read_json(basis['path'])
    require(previous['normal_cleanup']['all_three_retained_handles_exited'] is True
        and previous['normal_cleanup']['tasks_absent'] is True and previous['normal_cleanup']['force_used'] is False,'CLOSED_PREDECESSOR_REQUIRED')
    connector=Path(context.P['paths']['connector_state'])
    require(connector.is_dir() and not any(connector.iterdir()),'UNSELECTED_CONNECTOR_NOT_EMPTY')
    cleanup_path=context.PUBLIC/'cleanup-nexus.json';cleanup=read_json(cleanup_path);require_tags(cleanup,context)
    proof_path=context.PUBLIC/'nexus-exit-proof.json'
    require(cleanup.get('kind')=='PHYSICAL_SUPERVISOR_COHORT_EXIT' and cleanup.get('force_used') is False
        and cleanup.get('task_stopped_confirmed') is True and cleanup['exit_proof_sha256']==sha(proof_path),
        'COHORT_CLEANUP_REQUIRED')
    validate_exit(context,read_json(proof_path))
    uninstall=read_json(context.PUBLIC/'lifecycle-nexus-uninstall-result.json')
    action=read_json(context.PUBLIC/'lifecycle-nexus-uninstall.json')
    require(uninstall['returncode']==0 and uninstall['task_name']==context.C['tasks']['nexus']['name']
        and uninstall['cleanup_proof_sha256']==sha(cleanup_path)==action['cleanup_proof_sha256'],
        'UNINSTALL_PROOF_REQUIRED')
    tasks={}
    for component in ('nexus','connector'):
        name=context.C['tasks'][component]['name']
        require(task_reader(name) is None,'TEMPORARY_TASK_STILL_PRESENT')
        tasks[component]={'name':name,'absent':True,'canonical_absence':absence(context,component),
            'basis':'COHORT_EXIT_AND_UNINSTALL' if component=='nexus' else 'CLOSED_PREDECESSOR_AND_FINITE_LOCAL_ONLY_LEDGER'}
    return tasks,inventory

def main():
    context=gate(parser().parse_args())
    from okto_nexus.adapters.outbound.service_manager.windows_tasks import WindowsTasks
    tasks,inventory=check(context,WindowsTasks().read)
    host,port=endpoint(context)
    with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1);probe.bind((host,port))
    retained=all(Path(context.P['paths'][k]).is_dir() for k in ('server_home','connector_state','private_evidence','public_evidence'))
    require(retained,'CAMPAIGN_DATA_DIRECTORY_MISSING')
    value={'status':'NORMAL_CLEANUP_CONFIRMED','tasks':tasks,'invocation_evidence':inventory,
        'data_directories_retained':True,'force_used':False,'observed_at':time.time(),
        'exclusive_port_probe_passed_not_reserved':port,'remote_helper_evidence':{'selected':False},
        'runtime_work_settlement':'NOT_ASSERTED','scope':'Service cohort exit and integration removal only; no M1 acceptance or accounting finality.'}
    public_save(context,'final-presence.json',value);print(json.dumps(value));return 0

if __name__=='__main__':raise SystemExit(main_guard(main))
