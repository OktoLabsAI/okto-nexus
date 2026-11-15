from pathlib import Path
from types import SimpleNamespace
import json
import pytest
import phase1 as p
import operator_bootstrap as boot
from request_context import Refused,public_save

@pytest.fixture
def x(tmp_path):
    public=tmp_path/'public';private=tmp_path/'private'
    public.mkdir();private.mkdir()
    value=SimpleNamespace(PUBLIC=public,PRIVATE=private,ROOT=tmp_path,CONTROL=tmp_path,
        plan_sha256='test',env=lambda:{},require_ready=lambda:{'ready':True},
        P={'service_context':{},'paths':{'server_home':str(tmp_path/'home'),'operator_home':str(tmp_path/'operator')},
           'bootstrap_seconds':120,'expected_server_id':'srv_test'},
        C={'steps':[{'component':'nexus','action':a,'argv':['qualified-python','service',a]} for a in ('install','start','stop','uninstall')]})
    public_save(value,'preparation.json',{'status':'PREPARED'})
    return value

def effects(monkeypatch,x):
    calls=[]
    monkeypatch.setattr(p,'pin',lambda v:None)
    monkeypatch.setattr(p,'canonical_absence',lambda *a:{'state':'stopped'})
    monkeypatch.setattr(p,'task_absent',lambda *a:True)
    monkeypatch.setattr(p,'port_free',lambda *a:True)
    class Child:
        def __init__(self,argv,**kw):
            calls.append(argv)
            kw['stdout'].write(b'{"state":"stopped"}')
        def wait(self):return 0
    monkeypatch.setattr(p.subprocess,'Popen',Child)
    return calls

def test_install_only_once(x,monkeypatch):
    calls=effects(monkeypatch,x)
    assert p.lifecycle(x,'install')['returncode']==0
    with pytest.raises(FileExistsError):p.lifecycle(x,'install')
    assert len(calls)==1

def test_unknown_absence_never_dispatches(x,monkeypatch):
    calls=effects(monkeypatch,x)
    def refuse(*a):raise Refused('OWNER_UNKNOWN')
    monkeypatch.setattr(p,'canonical_absence',refuse)
    with pytest.raises(Refused):p.lifecycle(x,'install')
    assert not calls and not (x.PUBLIC/'install-reserved.json').exists()

def test_changed_context_never_dispatches(x,monkeypatch):
    calls=effects(monkeypatch,x)
    def refuse(*a):raise Refused('PIN_CHANGED')
    monkeypatch.setattr(p,'pin',refuse)
    with pytest.raises(Refused):p.lifecycle(x,'install')
    assert not calls

def test_start_requires_successful_install(x,monkeypatch):
    calls=effects(monkeypatch,x)
    public_save(x,'install-returned.json',{'returncode':3})
    with pytest.raises(Refused):p.lifecycle(x,'start')
    assert not calls

def test_uninstall_requires_full_physical_proof(x,monkeypatch):
    calls=effects(monkeypatch,x)
    public_save(x,'cleanup.json',{})
    def refuse(*a):raise Refused('PHYSICAL_EXIT_REQUIRED')
    monkeypatch.setattr(p,'cleanup_valid',refuse)
    with pytest.raises(Refused):p.lifecycle(x,'uninstall')
    assert not calls

def test_existing_account_without_own_profile_never_rotates(x,monkeypatch):
    calls=[]
    monkeypatch.setattr(boot,'commands',lambda X:('http://127.0.0.1:58631','m1-sonnet-human',[],[]))
    def http(origin,method,route,body,deadline):
        calls.append(method)
        return {'ok':True,'data':{'local':True,'configured':True}}
    monkeypatch.setattr(boot,'http',http)
    monkeypatch.setattr(boot,'bootstrap',lambda *a,**kw:pytest.fail('no bootstrap allowed'))
    with pytest.raises(Refused):p.operator(x)
    assert calls==['GET']

def test_bootstrap_command_alias_and_utf8_no_password_argv(x):
    x.P.update(topology={'origin':'http://127.0.0.1:58631'},
        operator_bootstrap={'username':'m1-sonnet-human','home':x.P['paths']['operator_home']},
        execution_bundle={'operator_profile':'m1-sonnet-human'},package_pins={'python':'qualified-python'})
    origin,name,login,verify=boot.commands(x)
    assert name=='m1-sonnet-human' and login[3:5]==['-X','utf8']
    assert '--password-stdin' in login and '--password' not in login
    assert 'status' in verify and origin=='http://127.0.0.1:58631'

def test_changed_cleanup_identity_refused(x,monkeypatch):
    cohort={r:{'pid':i+1,'birth':100+i} for i,r in enumerate(p.ROLES)}
    public_save(x,'nexus-owner-selection.json',{'cohort':cohort})
    bad={r:{**v,'physical_exit':True} for r,v in cohort.items()}
    bad['child']['birth']+=1
    public_save(x,'nexus-exit-proof.json',{'cohort':cohort,'exits':bad})
    with pytest.raises(Refused):p.cleanup_valid(x)
