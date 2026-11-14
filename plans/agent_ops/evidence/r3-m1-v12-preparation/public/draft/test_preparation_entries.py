"""Real Python entry denial only; no product import or authorized campaign."""
from pathlib import Path
import hashlib
import json
import subprocess

import pytest

D=Path(__file__).resolve().parent
P=D/'m1-codex-campaign-proposal-v12.json'
INSTALL=D/'installation'


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def environment():
    return json.loads((INSTALL/'environment.json').read_bytes())


def unchanged():
    p=json.loads(P.read_bytes())
    assert not Path(p['paths']['campaign_root']).exists()
    assert not any((INSTALL/n).exists() for n in (
        'installation-reserved.json','installation-result.json','installation-unknown.json'))
    return p


@pytest.mark.parametrize('script,selection',[
    ('m1_v12_lifecycle.py',['initialize']),
    ('m1_v12_setup.py',['local']),
    ('m1_v12_remote_setup.py',['transfer']),
    ('m1_v12_work.py',['local','useful']),
])
@pytest.mark.parametrize('case,expected',[
    ('missing','AUTHORIZATION_REQUIRED'),
    ('wrong_receipt','APPROVAL_SCOPE_MISMATCH'),
    ('wrong_proposal','PROPOSAL_HASH_MISMATCH'),
])
def test_actual_python_entry_refuses_before_campaign_or_product(tmp_path,script,selection,case,expected):
    p=unchanged()
    invalid=tmp_path/'invalid.json';invalid.write_bytes(b'{}')
    argv=[p['package_pins']['python'],'-I','-B',str(D/script),
          '--proposal',str(P),'--expected-proposal-sha256','0'*64 if case=='wrong_proposal' else sha(P),*selection]
    if case=='wrong_receipt':argv+=['--approval-path',str(invalid),'--approval-sha256',sha(invalid)]
    result=subprocess.run(argv,cwd=tmp_path,env=environment(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                          creationflags=subprocess.CREATE_NO_WINDOW,check=False)
    assert result.returncode==2
    assert json.loads(result.stdout)=={'status':'REFUSED_BEFORE_DISPATCH','code':expected}
    assert not result.stderr
    unchanged()


def test_actual_installer_execute_without_approval_refuses_before_reservation(tmp_path):
    p=unchanged()
    result=subprocess.run([p['package_pins']['python'],'-I','-B',str(INSTALL/'timed_install.py'),
        '--proposal',str(P),'--expected-proposal-sha256',sha(P),'--execute'],
        cwd=tmp_path,env=environment(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW,check=False)
    assert result.returncode==2 and b'--approval-path' in result.stderr and not result.stdout
    unchanged()


def test_actual_installer_candidate_gate_never_materializes_an_install(tmp_path):
    p=unchanged()
    invalid=tmp_path/'invalid.json';invalid.write_bytes(b'{}')
    result=subprocess.run([p['package_pins']['python'],'-I','-B',str(INSTALL/'timed_install.py'),
        '--proposal',str(P),'--expected-proposal-sha256',sha(P),
        '--approval-path',str(invalid),'--approval-sha256',sha(invalid),'--execute'],
        cwd=tmp_path,env=environment(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW,check=False)
    assert result.returncode==2
    value=json.loads(result.stdout)
    assert value['status']=='REFUSED_OR_INCOMPLETE' and value['reservation_exists'] is False
    assert value['retry_allowed'] is False
    assert value['code'] in ('V12_FINAL_PINS_REQUIRED','APPROVAL_REQUIRED')
    unchanged()


@pytest.mark.parametrize('key,selection',[
    ('root_driver_operator_bootstrap',['once']),
    ('root_driver_invoke',['operator_bootstrap','once']),
])
@pytest.mark.parametrize('case',['missing','wrong_receipt','wrong_proposal'])
def test_operator_and_invoke_real_entries_refuse_before_any_effect(tmp_path,key,selection,case):
    p=unchanged();invalid=tmp_path/'invalid-receipt.json';invalid.write_bytes(b'{}')
    argv=[p['package_pins']['python'],'-I','-B',p['execution_bundle']['files'][key]['path'],
        '--proposal',str(P),'--expected-proposal-sha256','0'*64 if case=='wrong_proposal' else sha(P),*selection]
    if case!='missing':argv+=['--approval-path',str(invalid),'--approval-sha256',sha(invalid)]
    result=subprocess.run(argv,cwd=tmp_path,env=environment(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW,check=False)
    assert result.returncode==2
    if case=='missing':assert b'--approval-path' in result.stderr and not result.stdout
    else:
        value=json.loads(result.stdout)
        assert value['status']=='REFUSED_OR_UNCONFIRMED'
        assert value['code']==('PROPOSAL_CHANGED' if case=='wrong_proposal' else 'FRESH_APPROVAL_SCOPE_REQUIRED')
        assert not result.stderr
    unchanged()
