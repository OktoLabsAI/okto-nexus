"""Synthetic only; network/process/password-vault effects are never permitted."""
from pathlib import Path
from types import SimpleNamespace
import json
import socket
import subprocess
import sys
import time
import urllib.request

import pytest

import driver_common as common
import invoke
import operator_bootstrap as op


@pytest.fixture(autouse=True)
def forbid_real_effects(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('REAL EFFECT FORBIDDEN')
    monkeypatch.setattr(subprocess, 'Popen', forbidden)
    monkeypatch.setattr(socket, 'socket', forbidden)
    monkeypatch.setattr(urllib.request, 'urlopen', forbidden)


@pytest.fixture
def ctx(tmp_path):
    for name in ('public', 'private', 'operator'):
        (tmp_path / name).mkdir()
    return SimpleNamespace(ROOT=tmp_path,
        args=SimpleNamespace(expected_proposal_sha256='a'*64, approval_sha256='b'*64),
        P={'topology': {'origin': 'http://127.0.0.1:57589'},
            'operator_bootstrap': {'username': 'm1v12-human', 'home': str(tmp_path / 'operator')},
            'paths': {'operator_home': str(tmp_path / 'operator')},
            'execution_bundle': {'operator_profile': 'm1v12-human'},
            'package_pins': {'python': 'synthetic-python'}},
        env=lambda: {'SYNTHETIC_ONLY': '1'})


def owner(*args):
    return {'pid': 77, 'generation': 'synthetic-generation', 'instance_id': 'synthetic-instance',
        'component': 'nexus', 'task': {'name': 'synthetic-task', 'digest': 'synthetic-digest'}}


class Effects:
    def __init__(self, ctx):
        self.ctx = ctx
        self.http = []
        self.cli = []
        self.phases = []
        self.lost = False
        self.initial = {'ok': True, 'data': {'configured': False, 'local': True}}
        self.after = {'ok': True, 'data': {'configured': True, 'local': True}}
        self.identity = dict(state='authenticated', origin='http://127.0.0.1:57589', server_id='server-test', profile='m1v12-human')

    def request(self, origin, method, route, body, deadline):
        self.http.append((origin, method, route, body))
        if method == 'POST':
            assert (self.ctx.ROOT / 'public/operator-account-reserved.json').exists()
            if self.lost:
                raise OSError('SYNTHETIC LOST RESPONSE')
            return self.after
        return self.initial if len(self.http) == 1 else self.after

    def run_cli(self, context, argv, secret, deadline):
        if secret is not None:
            assert (context.ROOT / 'public/operator-login-reserved.json').exists()
        self.cli.append((argv, secret))
        return dict(self.identity)

    def guard(self, phase):
        name = 'operator-account-reserved.json' if phase == 'producer' else 'operator-login-reserved.json'
        assert (self.ctx.ROOT / 'public' / name).exists()
        self.phases.append(phase)
        return True

    def run(self, **overrides):
        kw = dict(effect_guard=self.guard, deadline_monotonic=time.monotonic()+20,
            request=self.request, run_cli=self.run_cli, observe=owner,
            password_factory=lambda: 'SYNTHETIC_MEMORY_SECRET_ONLY')
        kw.update(overrides)
        return op.bootstrap(self.ctx, 'server-test', **kw)


@pytest.mark.parametrize('lost', [False, True])
def test_once_with_read_only_lost_response_recovery(ctx, lost):
    effects = Effects(ctx); effects.lost = lost
    result = effects.run()
    assert result['status'] == 'OPERATOR_AUTHENTICATED'
    assert effects.phases == ['producer', 'consumer']
    assert [v[1] for v in effects.http] == (['GET', 'POST', 'GET'] if lost else ['GET', 'POST'])
    assert len(effects.cli) == 2
    assert effects.cli[0][1] == effects.http[1][3]['password']
    assert effects.cli[1][1] is None
    assert all('SYNTHETIC_MEMORY_SECRET_ONLY' not in json.dumps(v) for v in (result, effects.cli[0][0]))
    assert all('SYNTHETIC_MEMORY_SECRET_ONLY' not in p.read_text() for p in (ctx.ROOT/'public').iterdir())
    with pytest.raises(common.Refused, match='REPLAY'):
        effects.run()
    assert sum(v[1]=='POST' for v in effects.http)==1


@pytest.mark.parametrize('data', [{'configured': True,'local':True}, {'configured':False,'local':False}, {'configured':0,'local':True}])
def test_existing_or_nonlocal_account_refuses_before_effect(ctx, data):
    effects=Effects(ctx); effects.initial={'ok':True,'data':data}
    with pytest.raises(common.Refused, match='FRESH_LOCAL_ACCOUNT_REQUIRED'):
        effects.run()
    assert len(effects.http)==1 and effects.cli==[] and effects.phases==[]


@pytest.mark.parametrize('phase', ['producer','consumer'])
def test_closed_fence_prevents_next_effect_without_replay(ctx, phase):
    effects=Effects(ctx)
    with pytest.raises(common.Refused, match='FENCE_CLOSED'):
        effects.run(effect_guard=lambda p:p!=phase)
    assert effects.cli==[]
    assert sum(v[1]=='POST' for v in effects.http)==(phase=='consumer')
    name='operator-account-reserved.json' if phase=='producer' else 'operator-login-reserved.json'
    assert (ctx.ROOT/'public'/name).exists()
    with pytest.raises(common.Refused,match='REPLAY'):effects.run()


@pytest.mark.parametrize('field,value', [('state','unknown'), ('server_id','other'), ('origin','http://127.0.0.1:1'), ('profile','other')])
def test_login_identity_mismatch_refuses(ctx, field, value):
    effects=Effects(ctx); effects.identity[field]=value
    with pytest.raises(common.Refused, match='LOGIN_IDENTITY'):
        effects.run()
    assert sum(v[1]=='POST' for v in effects.http)==1


def test_owner_change_before_create_refuses(ctx):
    effects=Effects(ctx); values=[owner(),dict(owner(),generation='different')]
    with pytest.raises(common.Refused,match='OWNER_CHANGED'):
        effects.run(observe=lambda *args:values.pop(0))
    assert effects.cli==[] and len(effects.http)==1


def test_lost_create_unconfirmed_never_logs_in(ctx):
    effects=Effects(ctx); effects.lost=True; effects.after={'ok':True,'data':{'configured':False,'local':True}}
    with pytest.raises(common.Refused,match='ACCOUNT_CREATE_UNCONFIRMED'):
        effects.run()
    assert effects.cli==[] and [v[1] for v in effects.http]==['GET','POST','GET']


def test_canonical_login_password_only_stdin(ctx):
    seen={}
    class Child:
        returncode=0
        def communicate(self, value):
            seen['input']=value
            return b'{"state":"authenticated"}',None
    def spawn(argv,**kw):
        seen.update(argv=argv,kwargs=kw)
        return Child()
    _,_,argv,_=op.commands(ctx)
    assert op.cli(ctx,argv,'SYNTHETIC_PASSWORD',time.monotonic()+20,popen=spawn)=={'state':'authenticated'}
    assert seen['input']==b'SYNTHETIC_PASSWORD\n'
    assert 'SYNTHETIC_PASSWORD' not in json.dumps(seen['argv'])
    assert seen['kwargs']['stderr']==subprocess.DEVNULL
    assert seen['kwargs']['env']=={'SYNTHETIC_ONLY':'1'}


def test_http_transport_no_redirect_proxy_or_cookie(monkeypatch):
    seen={}
    class Response:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self,size):return b'{"ok":true}'
    class Opener:
        def open(self,request,timeout):
            seen['request']=request; seen['timeout']=timeout
            return Response()
    def build(*handlers):seen['handlers']=handlers;return Opener()
    monkeypatch.setattr(op,'build_opener',build)
    assert op.http('http://127.0.0.1:57589','GET','/api/v1/operator-auth/status',None,time.monotonic()+20)=={'ok':True}
    handlers=seen['handlers']
    assert handlers[0].proxies=={} and isinstance(handlers[1],op.NoRedirect)
    assert handlers[1].redirect_request(None,None,None,None,None,None) is None
    assert dict(seen['request'].header_items())=={'Origin':'http://127.0.0.1:57589','X-nexus-ui':'1','Content-type':'application/json'}


def test_new_invoke_selection_is_pinned(ctx,tmp_path):
    path=tmp_path/'synthetic-wrapper.py';path.write_text('# inert')
    ctx.P['execution_bundle']['files']={'root_driver_operator_bootstrap':{'path':str(path),'sha256':common.sha(path)}}
    ctx.common_args=lambda:['--synthetic']
    argv,stdin=invoke.select(ctx,'operator_bootstrap',['once'])
    assert argv==['synthetic-python','-I','-B',str(path),'--synthetic','once'] and stdin is None
    path.write_text('# modified')
    with pytest.raises(common.Refused,match='SELECTED_MODULE_CHANGED'):
        invoke.select(ctx,'operator_bootstrap',['once'])


def test_existing_monitor_observes_during_account_and_login_without_admission(ctx):
    module_root=Path('C:/Users/jpamb/AppData/Local/Temp/m1-v12-bundle-bldo9qy7/draft')
    sys.path.insert(0,str(module_root))
    from remote_transfer_monitor import transfer_with_monitor
    class Fence:
        def arm(self,deadline):self.deadline=deadline
        def require(self,method):assert method=='POST'
    controller=SimpleNamespace(fence=Fence(),fault=lambda code:pytest.fail(code))
    effects=Effects(ctx); observed=[]
    def poll():
        observed.append((len(effects.http),len(effects.cli)))
        return {'can_admit':True,'current':[],'known_observed_tokens':89473}
    original=effects.request
    def slow_http(*args):
        result=original(*args);time.sleep(.03);return result
    original_cli=effects.run_cli
    def slow_cli(*args):
        result=original_cli(*args);time.sleep(.03);return result
    result,monitor=transfer_with_monitor(controller=controller,poll=poll,interval=.01,
        transfer=lambda **kw:effects.run(request=slow_http,run_cli=slow_cli,**kw))
    assert result['status']=='OPERATOR_AUTHENTICATED' and result['model_admissions']==0
    assert monitor['worker_joined'] and monitor['ordered_effect_gates_passed'] and not monitor['fence_selected']
    assert any(h>=2 and c==0 for h,c in observed) and any(c==1 for h,c in observed)


def test_monitor_blocks_login_when_historical_usage_closes_gate(ctx):
    sys.path.insert(0,'C:/Users/jpamb/AppData/Local/Temp/m1-v12-bundle-bldo9qy7/draft')
    from remote_transfer_monitor import transfer_with_monitor
    faults=[]
    controller=SimpleNamespace(fence=SimpleNamespace(arm=lambda _:None,require=lambda _:None),fault=faults.append)
    effects=Effects(ctx)
    result,monitor=transfer_with_monitor(controller=controller,
        poll=lambda:{'can_admit':len(effects.http)<2,'current':[]},interval=.01,
        transfer=lambda **kw:effects.run(**kw))
    assert monitor['worker_joined'] and monitor['fence_selected'] and faults
    assert effects.cli==[] and sum(v[1]=='POST' for v in effects.http)==1


@pytest.mark.parametrize('origin', ['http://example.com:57589','https://127.0.0.1:57589','http://127.0.0.1:57589/other'])
def test_noncanonical_origin_refuses_before_http(ctx,origin):
    ctx.P['topology']['origin']=origin
    effects=Effects(ctx)
    with pytest.raises(common.Refused):effects.run()
    assert effects.http==[]


@pytest.mark.parametrize('code,raw', [(3,b'{}'),(0,b'not JSON')])
def test_cli_bad_response_never_claims_authenticated(ctx,code,raw):
    child=SimpleNamespace(returncode=code,communicate=lambda _: (raw,None))
    with pytest.raises((common.Refused,ValueError)):
        op.cli(ctx,['synthetic'],'SYNTHETIC_PASSWORD',time.monotonic()+10,popen=lambda *a,**k:child)


def test_expired_deadline_prevents_process_and_http(ctx):
    def forbidden(*a,**k):pytest.fail('effect after deadline')
    with pytest.raises(common.Refused,match='DEADLINE'):
        op.cli(ctx,['synthetic'],'SYNTHETIC_PASSWORD',time.monotonic()-1,popen=forbidden)
    with pytest.raises(common.Refused,match='DEADLINE'):
        op.http('http://127.0.0.1:57589','GET','/api/v1/operator-auth/status',None,time.monotonic()-1)


def test_existing_operator_profile_refuses_without_reading_secret(ctx):
    path=Path(ctx.P['paths']['operator_home'])/'terminal/operators/m1v12-human.json'
    path.parent.mkdir(parents=True);path.write_text('NOT READ')
    effects=Effects(ctx)
    with pytest.raises(common.Refused,match='PROFILE_ALREADY_EXISTS'):effects.run()
    assert effects.http==[]


@pytest.mark.parametrize('failure',[False,True])
def test_execute_uses_existing_history_and_closes_controller_before_return(ctx,monkeypatch,failure):
    from types import ModuleType
    ctx.modules=ctx.ROOT
    ctx.P['paths'].update(server_home=str(ctx.ROOT/'server'),connector_state=str(ctx.ROOT/'connector'))
    ctx.P['controller_preparation']={'policy':{'revision':12,'carry_in_tokens':89473}}
    ctx.P['execution_bundle']['files']={'context':{'path':str(ctx.ROOT/'context.py')},
        'remote_canonical_recipe':{'path':str(ctx.ROOT/'recipe.json')}}
    origin,_,login,verify=op.commands(ctx)
    (ctx.ROOT/'recipe.json').write_text(json.dumps({'format':'m1-v12-readonly-remote-recipe','proposal_revision':12,
        'limits':{'policy':ctx.P['controller_preparation']['policy']},'operator_bootstrap':{
            'login':{'argv':login},'verify_login_argv':verify,
            'read_first':{'url':origin+'/api/v1/operator-auth/status'},
            'create_once':{'url':origin+'/api/v1/operator-auth/account'}}}))
    common.public_save(ctx,'root-driver-preparation.json',{'synthetic':True})
    (ctx.ROOT/'private/controller.json').write_text('SYNTHETIC EXISTENCE ONLY')
    trace=[]
    controller=SimpleNamespace(
        data={'requests':{'local':{'kind':'work','lane':'local','scope':{'server_id':'server-test'}}}},
        attach_owner=lambda *a:trace.append('attach_owner'),
        fence=SimpleNamespace(arm=lambda _:None,require=lambda _:None),
        fault=lambda _:trace.append('fault'),close=lambda:trace.append('close'),
        poll=lambda:{'can_admit':True,'current':[],'known_observed_tokens':89473})
    def get_controller(*,create):
        assert create is False
        trace.append('load_existing')
        return controller
    ctx.controller=get_controller;ctx.stop_argv=lambda component:['synthetic-stop',component]
    history=ModuleType('history_observers')
    def attach(value,**kwargs):
        assert value is controller and kwargs['campaign_root']==ctx.ROOT
        trace.append('attach_history');return ['local']
    history.attach_existing_work=attach
    monkeypatch.setitem(sys.modules,'history_observers',history)
    sys.path.insert(0,'C:/Users/jpamb/AppData/Local/Temp/m1-v12-bundle-bldo9qy7/draft')
    def bootstrap(value,expected,**kwargs):
        assert value is ctx and expected=='server-test'
        assert kwargs['effect_guard']('producer')
        if failure:raise OSError('SYNTHETIC SECRET MUST NOT APPEAR')
        assert kwargs['effect_guard']('consumer')
        return {'status':'OPERATOR_AUTHENTICATED','model_admissions':0}
    monkeypatch.setattr(op,'bootstrap',bootstrap)
    def spawn(argv,**kwargs):
        assert argv==['synthetic-stop','nexus']
        trace.append('normal_stop');return SimpleNamespace(poll=lambda:0)
    monkeypatch.setattr(op.subprocess,'Popen',spawn)
    if failure:
        with pytest.raises(common.Refused,match='OPERATOR_BOOTSTRAP_UNCONFIRMED'):op.execute(ctx)
        assert trace.count('normal_stop')==1
        assert 'SYNTHETIC SECRET MUST NOT APPEAR' not in (ctx.ROOT/'public/operator-bootstrap-unconfirmed.json').read_text()
    else:
        assert op.execute(ctx)['status']=='OPERATOR_AUTHENTICATED'
        assert 'normal_stop' not in trace
    assert trace[:3]==['load_existing','attach_owner','attach_history'] and trace[-1]=='close'
