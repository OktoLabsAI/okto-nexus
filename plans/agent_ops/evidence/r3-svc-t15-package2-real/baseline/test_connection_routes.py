import copy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

spec=importlib.util.spec_from_file_location('svc15_resume02',Path(__file__).with_name('connection_case.py'))
C=importlib.util.module_from_spec(spec);spec.loader.exec_module(C)


@pytest.fixture
def actual_options(monkeypatch):
    """Run the installed projection, replacing its IO/authority dependencies only."""
    import okto_nexus.application.execution_runtime_options as options
    import okto_nexus.application.execution_agent_recovery as recovery
    import okto_nexus.application.agent_execution_policy as policy
    import okto_nexus.application.execution_harness_configuration as harness
    import nexus_connector_core as core
    technical={'adapter_id':'codex_app_server','candidate_ref':'fixture-ref','label':'fixture native',
        'state':'NOT_PROBED','trust':'selected','reasons':[],'version':None}
    snapshot={'inventory_revision':'fixture-revision','catalog':{'runtimes':[{'adapter_id':'codex_app_server','support_status':'managed_supported'}]},
        'availability':{'availability':[technical]},
        'observations':[{'adapter_id':'codex_app_server','state':'PRESENT'}],
        'evidence':[{'adapter_id':'codex_app_server','candidate_ref':'fixture-ref','content_fingerprint':'private-not-public'}]}
    view={'snapshot':snapshot,'freshness':'FRESH','adapter_freshness':{'codex_app_server':'FRESH'}}
    monkeypatch.setattr(options,'read_executor_inventory',lambda *a,**k:copy.deepcopy(view))
    monkeypatch.setattr(options,'load_current_executor_inventory',lambda data:json.loads(data))
    monkeypatch.setattr(options,'_require_binding_method',lambda *a,**k:None)
    monkeypatch.setattr(recovery,'agent_recovering',lambda *a,**k:False)
    monkeypatch.setattr(policy,'require_execution_location',lambda *a,**k:None)
    monkeypatch.setattr(harness,'approvals_routing_enabled',lambda *a:False)
    monkeypatch.setattr(core,'discover_harness_configuration',lambda *a,**k:{'fixture':True})
    monkeypatch.setattr(core,'discover_provider_home',lambda *a,**k:{'fixture_only':True})
    class Connection:
        def execute(self,sql,values):
            assert sql.startswith('SELECT kind,control_state FROM execution_executors')
            return SimpleNamespace(fetchone=lambda:{'kind':'embedded','control_state':'CONTROL_READY'})
    class Unit:
        connection=Connection()
        def __enter__(self):return self
        def __exit__(self,*args):return False
    factory=SimpleNamespace(unit_of_work=lambda:Unit())
    access=SimpleNamespace(authenticate=lambda *a,**k:True,
        config=SimpleNamespace(feature_harness_integrations=True),
        agents=SimpleNamespace(get=lambda *a:SimpleNamespace(is_active=True)),require_admission=lambda *a:None)
    def project():
        return options.read_runtime_options(factory,server_id='server',executor_id='executor',agent_id='operator',
            workspace_id=None,fresh_publications={},context=SimpleNamespace(actor_agent_id='operator'),
            access=access,remote_ready=True)
    return project,factory,access


def test_installed_dashboard_route_and_projection_match_real_terminal_options(actual_options,monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from okto_nexus.adapters.inbound.http import dashboard_runtime,runtime_v1
    from okto_nexus.application.terminal_connection import TerminalConnection
    project,factory,access=actual_options
    router=dashboard_runtime.build_router()
    names={r.name for r in router.routes}
    assert 'runtime_options' in names and 'inventory_view' not in names
    monkeypatch.setattr(runtime_v1,'get_authenticated_agent',lambda:object())
    monkeypatch.setattr(runtime_v1,'ensure_execution_installation',lambda factory:SimpleNamespace(server_id='server'))
    monkeypatch.setattr(runtime_v1,'runtime_request_context',lambda:SimpleNamespace(actor_agent_id='operator'))
    monkeypatch.setattr(runtime_v1,'build_execution_access',lambda deps:access)
    monkeypatch.setattr(runtime_v1,'protocol_info',lambda:{'remote_execution_ready':True})
    app=FastAPI();app.state.deps=SimpleNamespace(connection_factory=factory);app.state.inventory_fresh_publications={}
    app.include_router(router,prefix=C.PREFIX)
    calls=[]
    with TestClient(app) as client:
        def transport(method,route,body=None):
            calls.append((method,route));response=client.request(method,route,json=body)
            assert response.status_code==200
            return response.json()
        flow=TerminalConnection(transport,lambda value:None)
        value=flow.options({'agent_id':'operator','executor_id':'executor'})
        assert value==project()
        assert 'snapshot' not in value and 'evidence' not in value
        selected=C.matching_candidate(value,{},'fixture-ref')
        assert selected['server_binary_fingerprint_observed'] is False
        assert calls==[('GET',C.PREFIX+'/agents/operator/runtime-options?executor_id=executor')]
        assert client.get(C.PREFIX+'/runtime/executors/executor/inventory').status_code==404


@pytest.mark.parametrize('change',['wrong_ref','untrusted','duplicate','not_present'])
def test_actual_projection_selection_rejects_changed_scope(actual_options,change):
    data=actual_options[0]()
    if change=='wrong_ref':data['options'][0]['candidate_ref']='other'
    elif change=='untrusted':data['availability']['availability'][0]['trust']='unselected'
    elif change=='duplicate':data['options'].append(copy.deepcopy(data['options'][0]))
    else:data['observations'][0]['state']='ABSENT'
    with pytest.raises(C.Refused):C.matching_candidate(data,{},'fixture-ref')


def test_pending_stale_then_real_projection_observer_uses_only_public_get(actual_options,tmp_path,monkeypatch):
    from okto_nexus.adapters.outbound import terminal_http
    import nexus_connector_core.installation as installation
    monkeypatch.setattr(C,'PUBLIC',tmp_path);monkeypatch.setattr(C,'sha',lambda path:'fixturehash')
    monkeypatch.setattr(installation,'installation_ref',lambda *args:'fixture-ref')
    monkeypatch.setattr(C.time,'sleep',lambda seconds:None)
    current=actual_options[0]();pending=copy.deepcopy(current);pending['adapter_freshness']['codex_app_server']='STALE'
    responses=iter([{'agent_id':'operator','server_id':'server'},
        {'items':[{'executor_id':'executor','kind':'embedded'}],'has_more':False},pending,current])
    calls=[]
    class HTTP:
        def __call__(self,method,route,body=None):calls.append((method,route));return next(responses)
    monkeypatch.setattr(terminal_http,'LocalOperatorHTTP',lambda **kwargs:HTTP())
    plan={'port':58981,'pins':{'native':{'path':'fixture-native','sha256':'fixturehash'}}}
    assert C.observe_candidate(plan)['candidate_ref']=='fixture-ref'
    assert all(method=='GET' for method,route in calls)
    assert all('/inventory' not in route for method,route in calls)
    assert len(json.loads((tmp_path/'http-observations.json').read_bytes()))==4


def test_only_unreachable_get_retries_within_one_deadline_and_keeps_sanitized_error():
    from okto_nexus.application.terminal_connection import ConnectionError
    clock=[0.0];records=[];calls=[]
    class HTTP:
        def __call__(self,method,route,body=None):
            calls.append(method)
            raise ConnectionError('SERVER_UNREACHABLE','DO NOT RETAIN SECRET MESSAGE',stage='http',possible_effect=False)
    http=C.ObservedHTTP(HTTP(),{},.5,clock=lambda:clock[0],sleep=lambda n:clock.__setitem__(0,clock[0]+n),record=records.append)
    with pytest.raises(C.Refused,match='HTTP_OBSERVATION_DEADLINE'):http('GET',C.PREFIX+'/connections/me')
    assert calls==['GET','GET'] and clock[0]==.5
    assert all(r['code']=='SERVER_UNREACHABLE' and r['stage']=='http' and r['possible_effect'] is False for r in records)
    assert 'SECRET' not in json.dumps(records)


@pytest.mark.parametrize('method,code,effect',[('GET','NOT_FOUND',False),('GET','AUTH_FAILED',False),('POST','OUTCOME_UNKNOWN',True)])
def test_other_get_errors_and_unknown_post_are_never_retried(method,code,effect,monkeypatch):
    from okto_nexus.application.terminal_connection import ConnectionError
    monkeypatch.setattr(C,'sha',lambda path:'approved')
    calls=[];records=[]
    class HTTP:
        def __call__(self,*args):calls.append(args);raise ConnectionError(code,'private',possible_effect=effect)
    http=C.ObservedHTTP(HTTP(),{'pins':{'native':{'path':'own','sha256':'approved'}}},120,
        clock=lambda:0,record=records.append,sleep=lambda _:pytest.fail('retry forbidden'))
    with pytest.raises(ConnectionError):http(method,C.PREFIX+'/connections/setup:test' if method=='POST' else C.PREFIX+'/connections/me',{})
    assert len(calls)==1 and len(records)==1


def test_changed_binary_refuses_before_cli_plan_or_post(monkeypatch):
    monkeypatch.setattr(C,'sha',lambda path:'changed')
    plan={'pins':{'native':{'path':'own','sha256':'approved'}}}
    with pytest.raises(C.Refused,match='APPROVED_NATIVE_BYTES_CHANGED'):
        C.setup_case(plan,lambda *args:pytest.fail('CLI plan selected'),None,None)
    http=C.ObservedHTTP(lambda *a:pytest.fail('POST selected'),plan,120,clock=lambda:0,record=lambda _:None)
    with pytest.raises(C.Refused,match='APPROVED_NATIVE_BYTES_CHANGED'):http('POST',C.PREFIX+'/connections/setup:test',{})


