"""Focused actual lifecycle wrapper dispatch tests; isolated fake context/effects only."""
from pathlib import Path
import hashlib,json,runpy,subprocess,sys,types
import pytest
D=Path(__file__).parent/'draft'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()

def execute(tmp_path,monkeypatch,proof,*,bad_pin=False,helper_refuses=False):
    root=tmp_path/'campaign';(root/'public').mkdir(parents=True);(root/'private').mkdir()
    source=tmp_path/'m1_v11_confirm_cleanup.py'
    source.write_text('def validate_never_started(X, proof, *, allow_current_uninstall=True):\n'
        '    assert allow_current_uninstall is True\n'
        '    X.calls.append("validate")\n'
        '    if X.helper_refuses: raise ValueError("PROOF_REFUSED")\n'
        '    return True\n')
    proof_path=root/'public/cleanup-nexus.json';proof_path.write_text(json.dumps(proof))
    X=types.SimpleNamespace(ROOT=root,P={'execution_bundle':{'files':{'root_driver_confirm_cleanup':
        {'path':str(source),'sha256':'0'*64 if bad_pin else sha(source)}}}},
        C={'steps':[{'component':'nexus','action':'uninstall','task_name':'own-task','argv':['synthetic-product','uninstall']}]},
        args=types.SimpleNamespace(expected_proposal_sha256='a'*64),remaining=['nexus','uninstall'],env=lambda:{},
        calls=[],helper_refuses=helper_refuses)
    def require(value,reason):
        if not value:raise ValueError(reason)
    def reserve(path,value):
        with Path(path).open('x') as f:json.dump(value,f)
    context=types.ModuleType('campaign_context');context.load=lambda:X;context.reserve_json=reserve;context.require=require
    monkeypatch.setitem(sys.modules,'campaign_context',context);monkeypatch.setattr(sys,'path',list(sys.path))
    class FakePopen:
        def __init__(self,argv,**kwargs):
            X.calls.append('popen');self.pid=12345;kwargs['stdout'].write(b'{"state":"uninstalled"}')
        def wait(self):return 0
    monkeypatch.setattr(subprocess,'Popen',FakePopen)
    error=None
    try:runpy.run_path(str(D/'m1_v11_lifecycle.py'),run_name='__main__')
    except BaseException as caught:error=caught
    return X,proof_path,error

@pytest.mark.parametrize('kind',['NEVER_STARTED_OWNER_ABSENT','physical'])
def test_uninstall_binds_the_exact_validated_proof_before_dispatch(tmp_path,monkeypatch,kind):
    proof={'component':'nexus','task_name':'own-task','force_used':False}
    if kind=='physical':proof.update(owned_pid_birth_exit_confirmed=True,task_stopped_confirmed=True)
    else:proof.update(kind=kind,owned_pid_birth_exit_confirmed=False)
    X,path,error=execute(tmp_path,monkeypatch,proof)
    assert isinstance(error,SystemExit) and error.code==0
    assert X.calls==(['validate','popen'] if kind!='physical' else ['popen'])
    for name in ('lifecycle-nexus-uninstall.json','lifecycle-nexus-uninstall-result.json'):
        assert json.loads((X.ROOT/'public'/name).read_bytes())['cleanup_proof_sha256']==sha(path)

@pytest.mark.parametrize('case',['validator_refuses','wrong_pin','unknown_kind','wrong_component','wrong_task'])
def test_uninstall_unknown_or_invalid_proof_never_reserves_or_dispatches(tmp_path,monkeypatch,case):
    proof={'kind':'NEVER_STARTED_OWNER_ABSENT' if case!='unknown_kind' else 'BOOLEANS_ARE_NOT_PROOF',
        'component':'nexus','task_name':'own-task','force_used':False,'owned_pid_birth_exit_confirmed':False}
    if case=='wrong_component':proof['component']='connector'
    if case=='wrong_task':proof['task_name']='different-task'
    X,path,error=execute(tmp_path,monkeypatch,proof,bad_pin=case=='wrong_pin',helper_refuses=case=='validator_refuses')
    assert isinstance(error,ValueError)
    assert 'popen' not in X.calls
    assert not (X.ROOT/'public/lifecycle-nexus-uninstall.json').exists()
