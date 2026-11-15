from types import SimpleNamespace
from unittest.mock import Mock
import sqlite3
import pytest
import post_context as C
import post_lifecycle as L


def cycle():return {'cycle_id':'old','phase':'running','attempts_started':1,'child_acknowledged':True,
    **{r:{'pid':i+1,'birth':123+i} for i,r in enumerate(C.ROLES)}}

def test_result_requires_all_real_svc20_facts():
    v={'next_connect_plan_sha256':'s','status':'PASS_SCOPED','configured_next_connect':True,'same_binding_grants':True,
       'both_connector_cohorts_exited':True,'connector_task_retained_inactive':True,'nexus_same_ready_cohort':True,
       'new_execution_operations':0,'force_used':False,'productive_start_selected':False,'provider_calls_selected':0}
    C.validate_result(v,'s')
    for k in ('both_connector_cohorts_exited','connector_task_retained_inactive','nexus_same_ready_cohort'):
        with pytest.raises(RuntimeError):C.validate_result({**v,k:False},'s')
    with pytest.raises(RuntimeError):C.validate_result({**v,'new_execution_operations':1},'s')


def test_all_three_exits_exact_births_required():
    selected={'cohort':cycle(),'next_connect_plan_sha256':'s'}
    proof={'cohort':cycle(),'next_connect_plan_sha256':'s','force_used':False,
        'exits':{r:{**cycle()[r],'physical_exit':True,'exit_code':0} for r in C.ROLES}}
    C.validate_exit(proof,selected,'s')
    proof['exits']['child']['birth']=999
    with pytest.raises(RuntimeError,match='PHYSICAL_EXIT'):C.validate_exit(proof,selected,'s')
    proof['exits'].pop('child')
    with pytest.raises(RuntimeError,match='INCOMPLETE'):C.validate_exit(proof,selected,'s')


def test_current_epoch_exact_own_sqlite_no_secret_fields(tmp_path):
    db=tmp_path/'own-fixture.db'
    with sqlite3.connect(db) as c:
        c.executescript('CREATE TABLE agents(agent_id TEXT,is_active INTEGER); CREATE TABLE execution_agent_revisions(agent_id TEXT,server_id TEXT,credential_epoch INTEGER);')
        c.execute('INSERT INTO agents VALUES (?,?)',('a',1));c.execute('INSERT INTO execution_agent_revisions VALUES (?,?,?)',('a','s',2))
    assert C.current_epoch(db,'s','a')==2
    with pytest.raises(RuntimeError,match='EPOCH2'):C.current_epoch(db,'other','a')
    with sqlite3.connect(db) as c:c.execute('UPDATE execution_agent_revisions SET credential_epoch=3')
    with pytest.raises(RuntimeError,match='EPOCH2'):C.current_epoch(db,'s','a')


def view(tmp_path):
    x=object.__new__(C.Context);x.PUBLIC=tmp_path/'post/public';x.PUBLIC.mkdir(parents=True);x.PRIVATE=tmp_path/'post/private';x.PRIVATE.mkdir()
    x.CONTROL=tmp_path/'post';x.ROOT=tmp_path;x.plan_sha256='life';x.post_plan_sha256='post'
    x.base=SimpleNamespace(PUBLIC=tmp_path/'old/public',require_tags=lambda v:C.require(v.get('lifecycle_plan_sha256')=='life','LIFECYCLE_TAG'),
      require_nexus_ready=Mock(return_value={'component':'nexus'}))
    return x


def test_connector_view_preserves_nexus_and_dual_tags(tmp_path):
    x=view(tmp_path);x.save('connector-owner-selection.json',{'x':1})
    value=C.read_json(x.PUBLIC/'connector-owner-selection.json');x.require_tags(value)
    assert value['lifecycle_plan_sha256']=='life' and value['post_svc20_plan_sha256']=='post'
    assert not x.base.PUBLIC.exists() and x.require_nexus_ready()=={'component':'nexus'}
    with pytest.raises(RuntimeError,match='RECEIPT_PLAN'):x.require_tags({'lifecycle_plan_sha256':'life'})


def test_single_start_reservation_and_no_install_receipt(tmp_path,monkeypatch):
    x=view(tmp_path);x.post_plan={'basis':{'svc20_result':{'sha256':'result'}}};x.require_pre_start=Mock(return_value={'zero_execution_operations':True})
    x.connector_env=lambda:{}
    monkeypatch.setattr(C.connector,'commands',lambda _: {'start':['python','canonical','daemon','start','--timeout','45']})
    calls=[]
    def spawn(argv,**kwargs):
        assert (x.PUBLIC/'connector-start-reserved.json').exists();calls.append(argv)
        kwargs['stdout'].write(b'{"state":"ready","generation":"new"}')
        return SimpleNamespace(wait=lambda:0)
    L.start(x,popen=spawn)
    assert len(calls)==1 and x.require_pre_start.call_count==2 and not (x.PUBLIC/'connector-install-returned.json').exists()
    with pytest.raises(RuntimeError,match='ALREADY_RESERVED'):L.start(x,popen=spawn)
    assert len(calls)==1


def test_second_guard_refusal_consumes_selection_without_spawn(tmp_path,monkeypatch):
    x=view(tmp_path);x.post_plan={'basis':{'svc20_result':{'sha256':'result'}}};x.require_pre_start=Mock(side_effect=[{},RuntimeError('changed')]);x.connector_env=lambda:{}
    monkeypatch.setattr(C.connector,'commands',lambda _:{'start':['python','start']});effect=Mock()
    with pytest.raises(RuntimeError,match='changed'):L.start(x,popen=effect)
    effect.assert_not_called();assert (x.PUBLIC/'connector-start-reserved.json').exists()


def test_old_cohort_select_never_publishes(tmp_path,monkeypatch):
    x=view(tmp_path);x.save('connector-start-returned.json',{'returncode':0})
    old={'generation':'g','cohort':cycle()};x.values={'after_connect':old};handles={r:Mock() for r in C.ROLES}
    monkeypatch.setattr(C.connector,'capture',lambda _: (old,handles))
    with pytest.raises(RuntimeError,match='FRESH_POST'):L.select(x)
    assert not (x.PUBLIC/'connector-owner-selection.json').exists()
    for h in handles.values():h.close.assert_called_once()


def test_new_cohort_select_publishes_after_validation(tmp_path,monkeypatch):
    x=view(tmp_path);x.save('connector-start-returned.json',{'returncode':0});x.values={'after_connect':{'generation':'old','cohort':cycle()}}
    new={'generation':'new','cohort':{**cycle(),'cycle_id':'new'}};handles={r:Mock() for r in C.ROLES}
    monkeypatch.setattr(C.connector,'capture',lambda _: (new,handles));L.select(x)
    value=C.read_json(x.PUBLIC/'connector-owner-selection.json');x.require_tags(value);assert value['generation']=='new'


def test_pre_start_drift_refuses_before_accounting(monkeypatch):
    x=object.__new__(C.Context);x.require_nexus_ready=Mock();x.base=SimpleNamespace(require_migrated=Mock())
    x.post_plan={'task_digest':'expected'}
    monkeypatch.setattr(C.connector,'installation',lambda _:SimpleNamespace(observe=lambda:(None,SimpleNamespace(enabled=True,active=True,digest='expected'))))
    with pytest.raises(RuntimeError,match='INSTALLED_IDLE'):x.require_pre_start()
    x.base.require_migrated.assert_called_once_with('connector')
