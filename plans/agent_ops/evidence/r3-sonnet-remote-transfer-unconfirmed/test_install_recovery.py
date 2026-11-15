from pathlib import Path
from types import SimpleNamespace
import json
import subprocess
import sys
import pytest
import recover_connector_install as r
from request_context import Refused,reserve

def test_actual_aborted_stdout_exact_sha_and_two_docs():
    raw=(r.HERE/'private/connector-install.stdout').read_bytes()
    plan=json.loads((r.HERE/'phase1-plan.json').read_text())
    assert r.decode_original(raw,plan['commands']['tasks']['connector'])['installed'] is False
    with pytest.raises(Refused):r.decode_original(raw+b' ',plan['commands']['tasks']['connector'])

@pytest.fixture
def X(tmp_path):
    public=tmp_path/'public';private=tmp_path/'private';public.mkdir();private.mkdir()
    x=SimpleNamespace(PUBLIC=public,PRIVATE=private,amendment_sha256=r.PLAN_SHA,python=sys.executable,
        P={'paths':{'connector_state':str(tmp_path/'connector')}},C={'tasks':{'connector':{'name':'task','instance_id':'svc_test'}}},
        require_tags=lambda v:None,require_ready=lambda:True)
    x.save=lambda name,v:reserve(public/name,dict(v,amendment_sha256=r.PLAN_SHA))
    x.save('connector-install-reserved.json',{'state':'RESERVED_BEFORE_DISPATCH','argv':r.commands(x)['install']})
    plan={'plan':{'name':'task','instance_id':'svc_test','admin_required':False,'mechanism':'windows-task-scheduler'}}
    (private/'connector-install.stdout').write_text(json.dumps(plan)+'\n'+json.dumps({'aborted':True,'installed':False}))
    return x

def dispatch(X,argv):
    assert argv.count('--non-interactive')==1
    (X.PRIVATE/'connector-install-recovery.stdout').write_text('{"installed":true}')
    (X.PRIVATE/'connector-install-recovery.stderr').write_text('')
    return 0

def test_one_success_truthful_recovery_receipt_no_original_rewrite(X):
    before=(X.PRIVATE/'connector-install.stdout').read_bytes();calls=[]
    def run(x,argv):calls.append(argv);return dispatch(x,argv)
    outcome=r.recover(X,dispatch=run,check_absent=lambda X:{'task_absent':True},
        check_installed=lambda X:{'state':'installed'},validate_original=r.decode_documents)
    assert outcome['status']=='RECOVERY_INSTALLED_CONFIRMED'
    value=json.loads((X.PUBLIC/'connector-install-returned.json').read_text())
    assert value['source']=='EXPLICIT_NONINTERACTIVE_RECOVERY'
    assert value['recovery_provenance']['original_attempt_success'] is False
    assert value['returncode']==0 and (X.PRIVATE/'connector-install.stdout').read_bytes()==before
    with pytest.raises(Refused):r.recover(X,dispatch=run)
    assert len(calls)==1

def test_absence_drift_after_reservation_no_dispatch(X):
    calls=[]
    def absent(X):
        calls.append('query')
        if len(calls)==2:raise Refused('TASK_APPEARED')
        return {'task_absent':True}
    with pytest.raises(Refused):r.recover(X,dispatch=lambda *a:pytest.fail('no dispatch'),
        check_absent=absent,validate_original=r.decode_documents)
    assert (X.PUBLIC/'connector-install-recovery-reserved.json').exists()
    assert not (X.PUBLIC/'connector-install-returned.json').exists()

def test_new_failed_install_never_creates_compatibility_success(X):
    def failed(x,argv):
        (x.PRIVATE/'connector-install-recovery.stdout').write_text('{"installed":false,"aborted":true}')
        (x.PRIVATE/'connector-install-recovery.stderr').write_text('')
        return 0
    with pytest.raises(Refused):r.recover(X,dispatch=failed,check_absent=lambda X:{},
        validate_original=r.decode_documents)
    assert json.loads((X.PUBLIC/'connector-install-recovery-returned.json').read_text())['status']=='UNCONFIRMED'
    assert not (X.PUBLIC/'connector-install-returned.json').exists()

def test_actual_isolated_bootstrap_help():
    value=subprocess.run([sys.executable,'-I','-B','-X','utf8',str(r.HERE/'recover_connector_install.py'),'--help'],capture_output=True)
    assert value.returncode==0 and b'--execute' in value.stdout
