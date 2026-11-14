"""Final real Python entry refusals; existing product installation is read-only."""
from pathlib import Path
import hashlib,json,subprocess
import pytest
S=Path(__file__).resolve().parent;D=S/'draft';B=S.parent
P=D/'m1-codex-campaign-proposal-v14.json'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def unchanged():
    p=json.loads(P.read_bytes())
    assert not (S/'public').exists() and not (S/'private').exists()
    for key in ('predecessor_checkpoint_pin','profile_pin'):
        pin=p['adoption'][key];assert sha(pin['path'])==pin['sha256']
    for pin in p['execution_bundle']['files'].values():assert sha(pin['path'])==pin['sha256']
    return p
def environment():return json.loads((B/'draft/installation/environment.json').read_bytes())
@pytest.mark.parametrize('script,selection',[
    ('m1_v14_lifecycle.py',['initialize']),('m1_v14_remote_setup.py',['transfer']),('m1_v14_work.py',['local','useful'])])
@pytest.mark.parametrize('case,expected',[('missing','AUTHORIZATION_REQUIRED'),('wrong_receipt','APPROVAL_SCOPE_MISMATCH'),('wrong_proposal','PROPOSAL_HASH_MISMATCH')])
def test_wrapper_refuses_before_successor_effect(tmp_path,script,selection,case,expected):
    p=unchanged();invalid=tmp_path/'invalid.json';invalid.write_bytes(b'{}')
    argv=[p['package_pins']['python'],'-I','-B',str(D/script),'--proposal',str(P),'--expected-proposal-sha256','0'*64 if case=='wrong_proposal' else sha(P),*selection]
    if case=='wrong_receipt':argv+=['--approval-path',str(invalid),'--approval-sha256',sha(invalid)]
    r=subprocess.run(argv,cwd=tmp_path,env=environment(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=subprocess.CREATE_NO_WINDOW,check=False)
    assert r.returncode==2 and json.loads(r.stdout)=={'status':'REFUSED_BEFORE_DISPATCH','code':expected} and not r.stderr
    unchanged()
@pytest.mark.parametrize('key,selection',[
    ('root_driver_operator_bootstrap',['once']),('root_driver_invoke',['adopt_local','once']),
    ('root_driver_adopt_local',['once']),('root_driver_authorize_local',['review'])])
@pytest.mark.parametrize('case',['missing','wrong_receipt','wrong_proposal'])
def test_driver_refuses_before_successor_effect(tmp_path,key,selection,case):
    p=unchanged();invalid=tmp_path/'invalid.json';invalid.write_bytes(b'{}')
    argv=[p['package_pins']['python'],'-I','-B',p['execution_bundle']['files'][key]['path'],'--proposal',str(P),'--expected-proposal-sha256','0'*64 if case=='wrong_proposal' else sha(P),*selection]
    if case!='missing':argv+=['--approval-path',str(invalid),'--approval-sha256',sha(invalid)]
    r=subprocess.run(argv,cwd=tmp_path,env=environment(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=subprocess.CREATE_NO_WINDOW,check=False)
    assert r.returncode==2
    if case=='missing':assert b'--approval-path' in r.stderr and not r.stdout
    else:
        assert json.loads(r.stdout)=={'status':'REFUSED_OR_UNCONFIRMED','code':'PROPOSAL_CHANGED' if case=='wrong_proposal' else 'FRESH_APPROVAL_SCOPE_REQUIRED'}
        assert not r.stderr
    unchanged()
