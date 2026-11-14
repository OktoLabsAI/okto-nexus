"""Synthetic ownership/control separation and immutable adoption proofs."""
from pathlib import Path
from copy import deepcopy
import hashlib,json,runpy,sys,types
import pytest
from campaign_context import verify_adoption,Refused

D=Path(__file__).parent/'draft'
def pin(path,value):
    path.write_text(json.dumps(value),encoding='utf-8')
    return {'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}

def proofs(root):
    old=pin(root/'proposal.json',{'revision':12,'paths':{'campaign_root':str(root/'old-home')}})
    checkpoint=pin(root/'checkpoint.json',{'preserved':'faulted predecessor'})
    presence=pin(root/'presence.json',{'all_absent':True})
    reservation=pin(root/'reservation.json',{'historic':True})
    closure={'campaign_revision':12,'format':'okto.m1.closed_campaign','status':'CLOSED_RECONCILED_CLEANUP_ACCEPTANCE_NOT_INFERRED','closed_without_force':True,'all_temporary_tasks_absent':True,'configured_setup_retained':True,'data_retained':True,'controller_mutated':False,'replay_allowed':False,'controller_checkpoint_sha256':checkpoint['sha256'],'final_presence_sha256':presence['sha256'],'cumulative_reserved_admissions':8,'cumulative_minimum_observed_tokens':111651,'proposal_sha256':old['sha256'],'approval_sha256':'b'*64}
    closure_pin=pin(root/'closure.json',closure)
    installed={'format':'okto.base06.installation','revision':1,'status':'INSTALLED_VERIFIED','proposal_revision':12,'proposal_sha256':old['sha256'],'approval_sha256':'b'*64,'campaign_root':str(root/'old-home'),'python':'synthetic-python','python_prefix':'synthetic-prefix','payload_count':983,'pip_check':{'returncode':0},'reservation_sha256':reservation['sha256']}
    install_pin=pin(root/'installed.json',installed)
    return {'adoption':{'predecessor_proposal_pin':old,'predecessor_closure_pin':closure_pin,'predecessor_checkpoint_pin':checkpoint,'predecessor_final_presence_pin':presence,'installation_result_pin':install_pin,'installation_reservation_pin':reservation},'package_pins':{'python':'synthetic-python','python_prefix':'synthetic-prefix'},'controller_preparation':{'ancestry':{'closure_sha256':closure_pin['sha256'],'checkpoint_sha256':checkpoint['sha256']}}}

def test_adoption_reads_exact_closed_predecessor_without_rewriting(tmp_path):
    p=proofs(tmp_path);before={f:f.read_bytes() for f in tmp_path.iterdir()}
    assert verify_adoption(p)['installation_adopted']
    assert {f:f.read_bytes() for f in tmp_path.iterdir()}==before

@pytest.mark.parametrize('change',['checkpoint','closure_tokens','install_scope','payload_count'])
def test_adoption_rejects_reset_or_different_installation(tmp_path,change):
    p=proofs(tmp_path);a=p['adoption']
    if change=='checkpoint':Path(a['predecessor_checkpoint_pin']['path']).write_text('{}')
    else:
        key='predecessor_closure_pin' if change=='closure_tokens' else 'installation_result_pin'
        path=Path(a[key]['path']);value=json.loads(path.read_bytes())
        value[{'closure_tokens':'cumulative_minimum_observed_tokens','install_scope':'campaign_root','payload_count':'payload_count'}[change]]={'closure_tokens':89473,'install_scope':'different-root','payload_count':982}[change]
        a[key]=pin(path,value)
    with pytest.raises(Refused):verify_adoption(p)

@pytest.mark.parametrize('change',[None,'fixture','report','existing_control'])
def test_initialize_only_creates_successor_evidence(tmp_path,monkeypatch,change):
    root=tmp_path/'ownership';root.mkdir();control=root/'successor13';control.mkdir()
    fixture=b'value\n1\n2\n3\n4\n';paths={}
    for lane in ('local_project','remote_project'):
        home=root/lane;home.mkdir();(home/'numbers.csv').write_bytes(fixture);paths[lane]=str(home)
    prior=root/'predecessor-checkpoint.json';prior.write_bytes(b'IMMUTABLE FAULTED PREDECESSOR')
    outputs={k:str(root/(k+'.json')) for k in ('local_output','connector_output')}
    if change=='fixture':(Path(paths['local_project'])/'numbers.csv').write_bytes(b'changed')
    if change=='report':Path(outputs['local_output']).write_bytes(b'existing')
    if change=='existing_control':(control/'private').mkdir()
    before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
    x=types.SimpleNamespace(ROOT=root,CONTROL=control,PUBLIC=control/'public',PRIVATE=control/'private',remaining=['initialize'],C={},args=types.SimpleNamespace(expected_proposal_sha256='a'*64,approval_sha256='b'*64),P={'paths':paths,'finite_work':{'fixture':{'numbers.csv':fixture.decode()},'delivery':outputs|{'expected_shape':{'input_sha256':hashlib.sha256(fixture).hexdigest()}}}})
    module=types.ModuleType('campaign_context');module.load=lambda:x
    def require(condition,code):
        if not condition:raise ValueError(code)
    module.require=require;module.reserve_json=lambda path,value:path.write_text(json.dumps(value))
    monkeypatch.setitem(sys.modules,'campaign_context',module)
    if change:
        with pytest.raises(ValueError):runpy.run_path(str(D/'m1_v13_lifecycle.py'),run_name='__main__')
        assert not x.PUBLIC.exists()
    else:
        runpy.run_path(str(D/'m1_v13_lifecycle.py'),run_name='__main__')
        assert x.PUBLIC.is_dir() and x.PRIVATE.is_dir()
        assert json.loads((x.PUBLIC/'authorization-reference.json').read_bytes())['control_root']==str(control)
    assert all(p.read_bytes()==v for p,v in before.items())
