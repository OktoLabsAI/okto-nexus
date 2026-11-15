from pathlib import Path
from types import SimpleNamespace
import hashlib
import importlib.util
import io
import json
import subprocess
import sys
import pytest
import connector_lifecycle as c
from request_context import Refused,reserve

HERE=Path(__file__).resolve().parent

@pytest.fixture
def receiver():
    path=HERE/'protected-transfer/protected_pty.py'
    spec=importlib.util.spec_from_file_location('test_receiver',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module

def test_actual_installed_material_sink_utf8_receiver(monkeypatch,receiver):
    from okto_nexus.adapters.inbound.cli.remote_setup_io import material_sink
    class TTY(io.StringIO):
        def isatty(self):return True
    stream=TTY();monkeypatch.setattr(sys,'stdin',TTY());monkeypatch.setattr(sys,'stdout',TTY());monkeypatch.setattr(sys,'stderr',stream)
    key='nxs_'+'a'*48
    material_sink(False)(key)
    actual=stream.getvalue()
    assert receiver.extract(actual)==key
    assert chr(0x2014) in receiver.HEADER

@pytest.mark.parametrize('mode',['missing_footer','duplicate_key','wrong_header'])
def test_receiver_refuses_ambiguous_material(receiver,mode):
    key='nxs_'+'b'*48
    text=receiver.HEADER+'\n'+key+'\n'+receiver.FOOTER
    if mode=='missing_footer':text=text.replace(receiver.FOOTER,'')
    elif mode=='duplicate_key':text+='\n'+key
    else:text=text.replace(chr(0x2014),'?')
    with pytest.raises(receiver.TransferError):receiver.extract(text)

@pytest.fixture
def X(tmp_path):
    public=tmp_path/'public';private=tmp_path/'private';root=tmp_path/'connector'
    public.mkdir();private.mkdir();root.mkdir()
    def save(name,value):reserve(public/name,dict(value,amendment_sha256='test'))
    def tags(v):
        if v.get('amendment_sha256')!='test':raise Refused('BAD_TAG')
    return SimpleNamespace(PUBLIC=public,PRIVATE=private,ROOT=tmp_path,python=sys.executable,
        P={'paths':{'connector_state':str(root)}},save=save,require_tags=tags,
        require_ready=lambda:True,connector_env=lambda:{})

def test_install_once_no_retry(X,monkeypatch):
    calls=[]
    monkeypatch.setattr(c,'canonical_absence',lambda *a:{})
    monkeypatch.setattr(c,'installation',lambda X:SimpleNamespace(observe=lambda:(None,None)))
    class Child:
        def __init__(self,argv,**kw):calls.append(argv);kw['stdout'].write(b'{"installed":true}')
        def wait(self):return 0
    monkeypatch.setattr(c.subprocess,'Popen',Child)
    assert c.lifecycle(X,'install')['returncode']==0
    with pytest.raises(FileExistsError):c.lifecycle(X,'install')
    assert len(calls)==1

def test_uninstall_preserves_absent_state(X,monkeypatch):
    from okto_nexus_connector.platform import paths
    state=Path(X.P['paths']['connector_state'])/'absent.json'
    monkeypatch.setattr(paths,'state_file',lambda root:state)
    monkeypatch.setattr(c,'cleanup_valid',lambda X:{})
    monkeypatch.setattr(c,'canonical_absence',lambda *a:{})
    monkeypatch.setattr(c,'installation',lambda X:SimpleNamespace(observe=lambda:(None,None)))
    X.save('connector-cleanup.json',{})
    class Child:
        def __init__(self,argv,**kw):kw['stdout'].write(b'{"removed":true}')
        def wait(self):return 0
    monkeypatch.setattr(c.subprocess,'Popen',Child)
    assert c.lifecycle(X,'uninstall')['returncode']==0
    result=json.loads((X.PUBLIC/'connector-final-presence.json').read_text())
    assert result['data']['exists'] is False and result['data_preserved'] is True

def test_cohort_mismatch_closes_acquired_handles(X,tmp_path):
    image=tmp_path/'python.exe';image.write_bytes(b'fixture')
    X.installed={'python_images':{str(image):hashlib.sha256(b'fixture').hexdigest()}}
    cohort={'phase':'running','child_acknowledged':True,'cycle_id':'cycle','attempts_started':1,
        **{r:{'pid':i+1,'birth':i+10} for i,r in enumerate(c.ROLES)}}
    closed=[]
    class Handle:
        def __init__(self,pid):self.pid=pid;self.birth=9+pid+(1 if pid==2 else 0);self.image=str(image)
        def exited(self):return False
        def close(self):closed.append(self.pid)
    with pytest.raises(Refused):c.capture(X,observe=lambda *a:{'pid':3},read_cycle=lambda X:cohort,process=Handle)
    assert closed==[1,2]

def test_cleanup_requires_all_roles(X):
    X.save('connector-owner-selection.json',{'cohort':{}})
    X.save('connector-exit-proof.json',{'cohort':{},'exits':{}})
    with pytest.raises(Refused):c.cleanup_valid(X)

def test_actual_isolated_transfer_entry_help():
    out=subprocess.run([sys.executable,'-I','-B','-X','utf8',str(HERE/'transfer_entry.py'),'--help'],capture_output=True)
    assert out.returncode==0 and b'transfer' in out.stdout
