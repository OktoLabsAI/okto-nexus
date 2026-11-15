"""One explicit install recovery after the preserved EOF/default-abort attempt."""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from request_context import require,read_json,sha
from transfer_context import TransferContext
from connector_lifecycle import commands,installation
from reused_observation import canonical_absence

HERE=Path(__file__).resolve().parent
PLAN_SHA='e56ae6fc22d5af02adc9687aaa8ee476846c1d7e09e43c030109cf9ec71820cd'
FREEZE_SHA='6bd4a176b1606ff3aa173e771b9c9a06eb3210dfe167701bdacbc2a060f71dc6'
ABORTED_STDOUT_SHA='78725844d03b6eedc15c140eb3fa1d7540ddcd34302aa22a74e9905fd334c441'

def decode_original(raw,expected):
    require(hashlib.sha256(raw).hexdigest()==ABORTED_STDOUT_SHA,'ORIGINAL_ABORT_BYTES_CHANGED')
    return decode_documents(raw,expected)

def decode_documents(raw,expected):
    require(len(raw)<=65536,'ORIGINAL_OUTPUT_TOO_LARGE')
    text=raw.decode('utf-8').lstrip();decoder=json.JSONDecoder()
    first,end=decoder.raw_decode(text);tail=text[end:].lstrip()
    second,end=decoder.raw_decode(tail)
    require(not tail[end:].strip() and set(first)=={'plan'}
        and second=={'aborted':True,'installed':False},'POSITIVE_ABORT_EVIDENCE_REQUIRED')
    plan=first['plan']
    require(plan.get('instance_id')==expected['instance_id'] and plan.get('name')==expected['name']
        and plan.get('admin_required') is False and plan.get('mechanism')=='windows-task-scheduler',
        'ABORTED_PLAN_SCOPE_CHANGED')
    return {'aborted':True,'installed':False,'json_documents':2,'instance_id':plan['instance_id'],'task_name':plan['name']}

def absent(X):
    owner=canonical_absence(X,'connector')
    _,task=installation(X).observe()
    require(task is None,'CONNECTOR_TASK_NOT_ABSENT')
    return {'owner':owner,'task_absent':True}

def installed(X):
    receipt,task=installation(X).observe()
    expected=X.C['tasks']['connector']
    require(receipt is not None and receipt.get('state')=='installed'
        and receipt.get('instance_id')==expected['instance_id'] and receipt.get('name')==expected['name']
        and task is not None and task.enabled and not task.active,'RECOVERY_INSTALLATION_UNCONFIRMED')
    canonical_absence(X,'connector')
    return {'instance_id':expected['instance_id'],'task_name':expected['name'],
        'task_enabled':True,'task_active':False,'task_digest':task.digest,'state':'installed'}

def run_cli(X,argv):
    with (X.PRIVATE/'connector-install-recovery.stdout').open('xb') as out,(X.PRIVATE/'connector-install-recovery.stderr').open('xb') as err:
        child=subprocess.Popen(argv,cwd=X.ROOT,env=X.connector_env(),stdin=subprocess.DEVNULL,
            stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
        return child.wait()

def recover(X,*,dispatch=run_cli,check_absent=absent,check_installed=installed,validate_original=decode_original):
    require(X.amendment_sha256==PLAN_SHA,'TRANSFER_PLAN_CHANGED')
    require(not (X.PUBLIC/'connector-install-returned.json').exists(),'INSTALL_RETURN_ALREADY_EXISTS')
    original=read_json(X.PUBLIC/'connector-install-reserved.json');X.require_tags(original)
    argv=commands(X)['install']
    require(original.get('state')=='RESERVED_BEFORE_DISPATCH' and original.get('argv')==argv,'ORIGINAL_SELECTION_CHANGED')
    aborted=validate_original((X.PRIVATE/'connector-install.stdout').read_bytes(),X.C['tasks']['connector'])
    X.require_ready();before=check_absent(X)
    updated=list(argv);updated.insert(updated.index('--json'),'--non-interactive')
    require(updated.count('--non-interactive')==1 and [v for v in updated if v!='--non-interactive']==argv,'RECOVERY_DELTA_CHANGED')
    command_sha=hashlib.sha256(json.dumps(updated,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
    X.save('connector-install-recovery-reserved.json',{'state':'RESERVED_BEFORE_DISPATCH','argv':updated,
        'command_sha256':command_sha,'original_stdout_sha256':ABORTED_STDOUT_SHA,'original_positive_abort':aborted,
        'fresh_absence':before,'provider_calls':0,'maximum_recovery_install_calls':1})
    # Recheck after durable reservation, immediately before the only new effect.
    X.require_ready();check_absent(X)
    rc=dispatch(X,updated)
    raw_path=X.PRIVATE/'connector-install-recovery.stdout'
    value={'returncode':rc,'stdout_sha256':sha(raw_path),
        'stderr_sha256':sha(X.PRIVATE/'connector-install-recovery.stderr'),
        'command_sha256':command_sha,'original_stdout_sha256':ABORTED_STDOUT_SHA,'original_aborted':True,
        'original_wrapper_failure':'JSONExtraData','provider_calls':0,'source':'EXPLICIT_NONINTERACTIVE_RECOVERY'}
    try:
        document=read_json(raw_path)
        require(rc==0 and document.get('installed') is True,'RECOVERY_INSTALL_CLI_FAILED')
        observation=check_installed(X)
    except Exception as error:
        X.save('connector-install-recovery-returned.json',dict(value,status='UNCONFIRMED',error_type=type(error).__name__))
        raise
    value.update(status='RECOVERY_INSTALLED_CONFIRMED',projection={'installed':True},canonical_observation=observation)
    X.save('connector-install-recovery-returned.json',value)
    # This pathname was absent. Its status is the actual recovery return, not a
    # rewrite or fabricated success of the original aborted command.
    compatible={**value,'recovery_provenance':{
        'actual_return_receipt':'connector-install-recovery-returned.json',
        'actual_return_receipt_sha256':sha(X.PUBLIC/'connector-install-recovery-returned.json'),
        'original_reservation':'connector-install-reserved.json','original_return_receipt_existed':False,
        'original_attempt_success':False,'original_positive_abort':aborted,
        'argv_delta':['--non-interactive'],'paid_admissions':0}}
    X.save('connector-install-returned.json',compatible)
    return {'status':value['status'],'returncode':rc,'provider_calls':0,'original_attempt_preserved':True}

def main():
    p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true',required=True);p.parse_args()
    require(sha(HERE/'transfer-freeze.json')==FREEZE_SHA,'TRANSFER_FREEZE_CHANGED')
    for value in read_json(HERE/'transfer-freeze.json')['files'].values():
        require(sha(value['path'])==value['sha256'],'FROZEN_ANCESTOR_CHANGED')
    X=TransferContext(HERE/'transfer-plan.json',PLAN_SHA)
    print(json.dumps(recover(X),ensure_ascii=False))
    return 0

if __name__=='__main__':raise SystemExit(main())
