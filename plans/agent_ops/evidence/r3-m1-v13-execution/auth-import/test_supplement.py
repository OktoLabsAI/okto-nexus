from pathlib import Path
import hashlib,json,subprocess,sys,types
import pytest
import supplement as s

HERE=Path(__file__).parent
M=json.loads((HERE/'manifest.json').read_bytes())
PY=M['python']

@pytest.mark.parametrize('preload',[False,True])
def test_real_fresh_isolated_import_reaches_controller_only_with_pinned_preload(tmp_path,preload):
    # Independent process starts with neither draft nor pytest's sys.path.
    # Stop at controller construction; no database, HTTP or service is touched.
    code=r'''
import sys,json,importlib.util,socket,subprocess
from pathlib import Path
manifest=json.loads(Path(sys.argv[1]).read_bytes())
def denied(*a,**k):raise AssertionError('EXTERNAL_EFFECT_FORBIDDEN')
socket.socket.connect=denied
class DeniedPopen(subprocess.Popen):
    def __init__(self,*a,**k):denied()
subprocess.Popen=DeniedPopen
sys.path.insert(0,str(Path(manifest['original_authorize']['path']).parent))
assert 'publication' not in sys.modules
if sys.argv[2]=='yes':
    spec=importlib.util.spec_from_file_location('tested_shim',manifest['shim']['path'])
    shim=importlib.util.module_from_spec(spec);spec.loader.exec_module(shim);driver=shim.prepare(manifest)
    assert Path(sys.modules['publication'].__file__).resolve()==Path(manifest['publication']['path']).resolve()
else:
    import authorize_local as driver
driver.read_json=lambda p:{};driver.require_tags=lambda *a:None;driver.status=lambda *a:{}
class Marker(Exception):pass
class Context:
    PUBLIC=Path('synthetic-public')
    modules=Path(manifest['controller_modules'])
    def controller(self,**kwargs):raise Marker()
try:driver.execute(Context(),'review')
except Marker:print('CONTROLLER_BOUNDARY_REACHED_NO_EFFECT')
except ModuleNotFoundError as error:print('IMPORT_REFUSED:'+error.name)
'''
    result=subprocess.run([PY,'-I','-B','-c',code,str(HERE/'manifest.json'),'yes' if preload else 'no'],cwd=tmp_path,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False,creationflags=subprocess.CREATE_NO_WINDOW)
    assert result.returncode==0 and not result.stderr
    assert result.stdout.strip()==(b'CONTROLLER_BOUNDARY_REACHED_NO_EFFECT' if preload else b'IMPORT_REFUSED:publication')

@pytest.mark.parametrize('mode,selection',[('work',['local','useful']),('authorize_local',['repeat']),('authorize_local',['review','apply'])])
def test_supplement_cannot_select_work_or_extra_phase(mode,selection):
    with pytest.raises(ValueError,match='SUPPLEMENT_SELECTION_INVALID'):
        s.select_shim(lambda *a:pytest.fail('selection escaped'),None,mode,selection,M,'manifest','a'*64)

@pytest.mark.parametrize('phase',['review','apply'])
def test_shim_preserves_exact_original_cli_and_only_adds_import_bootstrap(phase):
    context=types.SimpleNamespace(P={'package_pins':{'python':PY}})
    original=[PY,'-I','-B',M['original_authorize']['path'],'--proposal','proposal','--approval-path','binding',phase]
    argv,stdin=s.select_shim(lambda *a:(original,None),context,'authorize_local',[phase],M,'manifest','a'*64)
    assert argv==[PY,'-I','-B',M['shim']['path'],'--manifest','manifest','--manifest-sha256','a'*64,*original[4:]]
    assert stdin is None and original[3]==M['original_authorize']['path']

def fixture(tmp_path,monkeypatch):
    import copy
    m=copy.deepcopy(M);control=tmp_path/'control';public=control/'public';private=control/'private';public.mkdir(parents=True);private.mkdir()
    x=types.SimpleNamespace(CONTROL=control,PUBLIC=public,PRIVATE=private,args=types.SimpleNamespace(expected_proposal_sha256=M['proposal_sha256'],approval_sha256=M['approval_sha256']))
    m['control_root']=str(control)
    common=types.ModuleType('driver_common');common.require_tags=lambda *args:None;monkeypatch.setitem(sys.modules,'driver_common',common)
    for key,pin in m['failed_attempt'].items():
        target=tmp_path/(key+'.json');target.write_bytes(Path(pin['path']).read_bytes());pin['path']=str(target)
    (public/'adopt-local-result.json').write_bytes(Path(M['control_root']).joinpath('public/adopt-local-result.json').read_bytes())
    cp=private/'controller.json';cp.write_text(json.dumps({'requests':{},'faults':[]}));m['before_controller_sha256']=s.sha(cp)
    profile=tmp_path/'profile.json';profile.write_bytes(b'{"state":"done"}')
    x.P={'adoption':{'profile_pin':{'path':str(profile),'sha256':s.sha(profile)}}}
    return x,m

def test_zero_effect_review_proof_accepts_only_unchanged_failed_import(tmp_path,monkeypatch):
    x,m=fixture(tmp_path,monkeypatch);s.review_before_dispatch(x,m)
    assert not list(x.PUBLIC.glob('authorize-local-*')) and not list(x.PRIVATE.glob('authorize-local-*'))

@pytest.mark.parametrize('mutation',['request','fault','reservation','result','profile','original_failure'])
def test_review_refuses_any_prior_effect_or_modified_evidence(tmp_path,monkeypatch,mutation):
    x,m=fixture(tmp_path,monkeypatch)
    if mutation in ('request','fault'):
        cp=x.PRIVATE/'controller.json';cp.write_text(json.dumps({'requests':{'x':{}} if mutation=='request' else {},'faults':['UNKNOWN'] if mutation=='fault' else []}));m['before_controller_sha256']=s.sha(cp)
    elif mutation in ('reservation','result'):(x.PUBLIC/('authorize-local-'+mutation+'.json')).write_text('{}')
    elif mutation=='profile':Path(x.P['adoption']['profile_pin']['path']).write_text('{}')
    else:Path(m['failed_attempt']['returned']['path']).write_text('{}')
    with pytest.raises(ValueError):s.review_before_dispatch(x,m)

def test_changed_shim_pin_is_refused_before_import(tmp_path):
    value=json.loads((HERE/'manifest.json').read_bytes());value['shim']['sha256']='0'*64
    path=tmp_path/'bad.json';path.write_text(json.dumps(value))
    with pytest.raises(ValueError,match='SUPPLEMENT_PIN_CHANGED'):s.verify_manifest(path,s.sha(path))

def test_existing_or_unconfirmed_apply_never_dispatches(tmp_path,monkeypatch):
    x,m=fixture(tmp_path,monkeypatch)
    monkeypatch.setattr(s,'supplemental_return',lambda *args:{'returncode':1})
    with pytest.raises(ValueError,match='SUPPLEMENT_REVIEW_UNCONFIRMED'):s.apply_before_dispatch(x,m)

def test_exit_proof_requires_retained_supplement_wrapper_exit(tmp_path,monkeypatch):
    x,m=fixture(tmp_path,monkeypatch);directory=tmp_path/'supplement';(directory/'runtime-private').mkdir(parents=True)
    monkeypatch.setattr(s,'HERE',directory)
    (directory/'runtime-private/authorize_local-review.reserved.json').write_text('{}')
    with pytest.raises(FileNotFoundError):s.exit_proof(x,m,'a'*64)
