"""Successor14 pure presence fixtures; reused profile and new request identities."""
from pathlib import Path
import importlib.util
import json
import pytest
import driver_common as common
import confirm_final_presence as presence
from test_drivers import context, seal, absent

COLLECTOR = Path('C:/Users/jpamb/AppData/Local/Temp/m1-v12-bundle-bldo9qy7/successor14/draft/controller/token_collector.py')
spec = importlib.util.spec_from_file_location('test_presence_collector', COLLECTOR)
collector = importlib.util.module_from_spec(spec); spec.loader.exec_module(collector)

def put(path, value):
    path.write_text(json.dumps(value), encoding='utf-8')

def invocation(c, directory, mode, selection):
    name = '-'.join([mode, *selection]); value = dict(common.tags(c), mode=mode, selection=selection)
    put(directory/(name+'.reserved.json'), value)
    put(directory/(name+'.returned.json'), dict(value, wrapper_exit_confirmed=True, returncode=0))

@pytest.fixture
def local_only(context, tmp_path, monkeypatch):
    c = context; directory = tmp_path/'driver/runtime-private'; directory.mkdir(parents=True)
    monkeypatch.setattr(common, 'HERE', directory.parent)
    c.P['paths'].update(server_home=str(c.ROOT/'server'), connector_state=str(c.ROOT/'connector'))
    c.P['execution_bundle']['profiles'] = {'local': 'm1v12-local'}
    c.P['request_ids']={'work':['m1v14-local-work-01','m1v14-local-work-02','m1v14-remote-work-01','m1v14-remote-work-02']}
    c.P['execution_bundle']['files']['controller_token_collector'] = {'path': str(COLLECTOR), 'sha256': common.sha(COLLECTOR)}
    scope = {k:'synthetic-'+k for k in collector.PRE_SCOPE}
    predecessor = c.ROOT/'previous.json'; put(predecessor, dict(all_temporary_tasks_absent=True, closed_without_force=True))
    c.P['adoption'] = {'expected_scope':scope, 'predecessor_closure_pin':{'path':str(predecessor),'sha256':common.sha(predecessor)}}
    for mode, selection in [('lifecycle',['initialize']), ('adopt_local',['once']),
        ('authorize_local',['review']), ('authorize_local',['apply']), ('work',['local','useful']),
        ('work',['local','continuation']), ('operator_bootstrap',['once'])]:
        invocation(c,directory,mode,selection)
    checkpoint = dict(format=11, root=str(c.ROOT), proposal_sha256=c.args.expected_proposal_sha256,
        authorization_sha256=c.args.approval_sha256, **c.P['controller_preparation'],
        owners={'local':c.P['paths']['server_home']}, faults=['SYNTHETIC_FAULT_PRESERVED'],
        independent_observation={'worker_in_flight':False}, independent_owner_stops={},
        requests={'m1v14-local-work-01':{'kind':'work','lane':'local','scope':scope,'settled':True}},
        collector=collector.checkpoint(collector.initial_state()))
    put(c.PRIVATE/'controller.json',seal(checkpoint))
    (c.ROOT/'operator').mkdir(); (c.ROOT/'operator/login-fixture').write_text('synthetic auth state presence only')
    return c,directory

def check(fixture, **kwargs):
    c,directory=fixture
    return presence.check_component(c,'connector', task_reader=lambda _:None,
        inventory=common.invocation_inventory(c,directory), absence=kwargs.get('absence',lambda c,k:absent(c,k)))

def test_local_work_and_operator_bootstrap_do_not_require_pristine_operator(local_only):
    c,_=local_only; before=common.sha(c.PRIVATE/'controller.json')
    result=check(local_only); proof=result['unselected_scope_evidence']
    assert proof['basis']=='CLOSED_PREDECESSOR_AND_COMPLETE_LOCAL_ONLY_SUCCESSOR'
    assert proof['operator_pristine_required'] is False
    assert proof['checkpoint_summary']['faults_preserved']==['SYNTHETIC_FAULT_PRESERVED']
    assert common.sha(c.PRIVATE/'controller.json')==before

@pytest.mark.parametrize('mode,selection', [('lifecycle',['connector','install']),('lifecycle',['connector','start']),
    ('work',['connector','useful']),('remote_setup',['transfer']),('plan',['remote_plan']),('plan',['connector_host_draft'])])
def test_every_remote_or_implicit_selection_refuses(local_only,mode,selection):
    invocation(*local_only,mode,selection)
    with pytest.raises(common.Refused,match='CONNECTOR_SELECTION_OR_UNKNOWN_EFFECT'):check(local_only)

def test_lost_local_wrapper_response_refuses(local_only):
    (local_only[1]/'work-local-useful.returned.json').unlink()
    with pytest.raises(common.Refused,match='INCOMPLETE_INVOCATION'):check(local_only)

@pytest.mark.parametrize('folder,name',[('public','remote-host-handoff.json'),('private','remote-protected-transfer.json'),('connector','state.json')])
def test_remote_effect_marker_or_state_refuses(local_only,folder,name):
    (local_only[0].ROOT/folder/name).write_text('{}')
    with pytest.raises(common.Refused):check(local_only)

@pytest.mark.parametrize('change',['scope','owner','worker','seal'])
def test_checkpoint_disagreement_refuses(local_only,change):
    c,_=local_only;p=c.PRIVATE/'controller.json'; value=json.loads(p.read_text())
    if change=='scope':value['requests']['m1v14-local-work-01']['scope']['binding_id']='other'
    if change=='owner':value['owners']['connector']='other'
    if change=='worker':value['independent_observation']['worker_in_flight']=True
    if change=='seal':value['state_sha256']='0'*64
    put(p,value if change=='seal' else seal(value))
    with pytest.raises(common.Refused):check(local_only)

def test_canonical_absence_is_still_required(local_only):
    def refuse(*_):raise common.Refused('OWNER_UNKNOWN')
    with pytest.raises(common.Refused,match='OWNER_UNKNOWN'):check(local_only,absence=refuse)

def test_inventory_change_during_absence_refuses(local_only):
    def change(c,k):
        invocation(*local_only,'remote_setup',['transfer']); return absent(c,k)
    with pytest.raises(common.Refused,match='LOCAL_ONLY_HISTORY_CHANGED'):check(local_only,absence=change)
