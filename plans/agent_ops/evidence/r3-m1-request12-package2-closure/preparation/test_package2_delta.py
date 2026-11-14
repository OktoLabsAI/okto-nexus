"""Only the successor path fence and technical predecessor guard, without live effects."""
from pathlib import Path
import hashlib,json,sys
from unittest.mock import patch
import pytest
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE));sys.path.insert(0,str(HERE/'modules'))
import request_context as context
from fresh_work_controller import FreshWorkController
from independent_controller import Controller,POLICY

def pin(path):return {'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
def save(path,value):path.write_text(json.dumps(value),encoding='utf-8');return pin(path)

def test_real_constructor_path_fence_only():
    control=HERE.parent
    with patch.object(Controller,'__init__',return_value=None) as parent:
        selected=FreshWorkController(HERE/'private/controller.json',control.parent,
            original_control_root=control,amendment_path=HERE/'amendment.json',amendment_sha256='fixture')
        assert selected.original_control_root==control
        assert parent.call_args.args[0]==HERE/'private/controller.json'
        with pytest.raises(Exception,match='NEW_WORK_CONTROLLER_PATH_INVALID'):
            FreshWorkController(control/'work-request12/private/controller.json',control.parent,
                original_control_root=control,amendment_path=HERE/'amendment.json',amendment_sha256='fixture')
        assert parent.call_count==1

def test_policy_and_fourteen_other_modules_unchanged():
    ancestry=json.loads((HERE/'source-ancestry.json').read_bytes())
    modules={k:v for k,v in ancestry['sources'].items() if Path(v['path']).parent==HERE/'modules'}
    assert len(modules)==15
    assert [k for k,v in modules.items() if not v['byte_equal']]==['fresh_work_controller']
    for key,value in modules.items():
        if key!='fresh_work_controller':assert pin(Path(value['path']))['sha256']==value['ancestor']['sha256']
    assert POLICY=={'revision':14,'carry_in_admissions':11,'carry_in_tokens':272648,
        'max_cumulative_admissions':13,'max_new_admissions':2,'preventive_cumulative_tokens':500000,
        'operational_tolerance':700000,'deadline_seconds':600}

def test_observed_real_technical_predecessor_remains_empty():
    assert context.verify_technical_predecessor(pin(HERE/'technical-predecessor.json')) is True

def predecessor_fixture(tmp_path,monkeypatch):
    monkeypatch.setattr(context,'CONTROL',tmp_path)
    root=tmp_path/'work-request12';root.mkdir()
    for folder in ('public','private','runtime-private'):(root/folder).mkdir()
    controller=root/'private/controller.json'
    save(controller,{'requests':{},'collector':{'state':{'requests':{}}},'faults':[],
        'policy':{'carry_in_tokens':272648,'carry_in_admissions':11}})
    for phase,code in (('plan',0),('apply',2)):
        save(root/'runtime-private'/('upgrade-'+phase+'.returned.json'),
            {'mode':'upgrade','selection':[phase],'returncode':code,'wrapper_exit_confirmed':True})
    save(root/'public/environment-upgrade-apply-result.json',{'returncode':2,
        'reported_code':'UPGRADE_ENVIRONMENT_UNAVAILABLE','service_started':False})
    proof={'root':str(root),'status':'SUPERSEDED_PREPARATION_NO_MODEL_OR_SERVICE_START',
        'controller':pin(controller),'directories':{folder:{p.name:pin(p) for p in (root/folder).iterdir()}
            for folder in ('public','private','runtime-private')}}
    target=tmp_path/'proof.json';save(target,proof)
    return root,target,proof

def test_new_selection_invalidates_observed_absence(tmp_path,monkeypatch):
    root,target,_=predecessor_fixture(tmp_path,monkeypatch)
    assert context.verify_technical_predecessor(pin(target))
    (root/'runtime-private/work-local-useful.reserved.json').write_text('{}')
    with pytest.raises(Exception,match='TECHNICAL_PREDECESSOR_SELECTION_CHANGED'):
        context.verify_technical_predecessor(pin(target))

def test_nonempty_controller_never_refunded_even_with_updated_file_pins(tmp_path,monkeypatch):
    root,target,proof=predecessor_fixture(tmp_path,monkeypatch)
    path=root/'private/controller.json';value=json.loads(path.read_bytes());value['requests']={'used':{}}
    updated=save(path,value);proof['controller']=updated;proof['directories']['private']['controller.json']=updated
    save(target,proof)
    with pytest.raises(Exception,match='PREDECESSOR_ALREADY_ADMITTED'):
        context.verify_technical_predecessor(pin(target))
