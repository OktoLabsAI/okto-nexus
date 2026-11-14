from pathlib import Path
from copy import deepcopy
from datetime import datetime,timedelta,timezone
import json,sys,types
import pytest
import extension as e

H=Path(__file__).parent;M=json.loads((H/'manifest.json').read_bytes())
sys.path.insert(0,str(Path(M['original_authorize']['path']).parent))
import driver_common

def fixture(tmp_path,monkeypatch):
    m=deepcopy(M);public=tmp_path/'public';private=tmp_path/'private';public.mkdir();private.mkdir()
    context=types.SimpleNamespace(PUBLIC=public,PRIVATE=private,CONTROL=tmp_path,args=types.SimpleNamespace(expected_proposal_sha256=m['proposal_sha256'],approval_sha256=m['approval_sha256']))
    m['control_root']=str(tmp_path)
    monkeypatch.setattr(driver_common,'require_tags',lambda *a:None)
    monkeypatch.setattr(driver_common,'tags',lambda c:{'synthetic':True})
    for key in ('old_public_review','old_controller','old_work_checkpoint','original_import_review_returned'):
        src=Path(m[key]['path']);dest=public/'authorize-local-review.json' if key=='old_public_review' else private/(key+'.json')
        dest.write_bytes(src.read_bytes());m[key]={'path':str(dest),'sha256':e.sha(dest)}
    review=e.read(m['old_public_review']['path'])['review']
    context.P={'adoption':{'expected_scope':review['scope']}}
    return context,m

def after(m):return datetime.fromisoformat(m['old_expiry'].replace('Z','+00:00'))+timedelta(seconds=1)

def test_exact_prior_review_after_clock_expiry_is_read_only(tmp_path,monkeypatch):
    c,m=fixture(tmp_path,monkeypatch);before={p:p.read_bytes() for p in tmp_path.rglob('*.json')}
    e.before_review(c,m,now=after(m))
    assert {p:p.read_bytes() for p in tmp_path.rglob('*.json')}==before

@pytest.mark.parametrize('change',['before_expiry','pending_submitted','pending_revision','work','request','fault','old_review_changed','issue_decision'])
def test_new_review_refuses_changed_history_or_possible_issue(tmp_path,monkeypatch,change):
    c,m=fixture(tmp_path,monkeypatch);now=after(m)
    if change=='before_expiry':now-=timedelta(seconds=2)
    elif change=='issue_decision':(c.PRIVATE/'authorize-local-reviewed.json').write_text('{}')
    elif change=='old_review_changed':Path(m['old_public_review']['path']).write_text('{}')
    else:
        key='old_controller' if change in ('request','fault') else 'old_work_checkpoint';path=Path(m[key]['path']);value=e.read(path)
        if change=='pending_submitted':value['authorization']['state']='submitted'
        elif change=='pending_revision':value['authorization']['review_revision']='wrong'
        elif change=='work':value['session_id']='unexpected'
        elif change=='request':value['requests']={'one':{}}
        elif change=='fault':value['faults']=['UNKNOWN']
        path.write_text(json.dumps(value));m[key]['sha256']=e.sha(path)
    with pytest.raises((ValueError,KeyError)):e.before_review(c,m,now=now)

def new_result(m):
    old=e.read(m['old_public_review']['path']);value=deepcopy(old)
    value['status']='EXPIRED_UNUSED_GRANT_REVIEWED';value['review']['current_grants'][0]['state']='expired'
    value['review']['can_issue']=True;value['review']['request']['client_request_id']='authorize_new_synthetic'
    value['review']['review_revision']='new-review';value['calls']={'review':1};return value

def original_driver():return e.load_pinned('test_original_authorize',M['original_authorize'])

def test_publication_preserves_old_bytes_and_versions_atomic_current(tmp_path,monkeypatch):
    c,m=fixture(tmp_path,monkeypatch);old=Path(m['old_public_review']['path']).read_bytes()
    result=new_result(m);e.publisher(c,m,'a'*64,original_driver())(c,'authorize-local-review.json',result)
    assert (c.PUBLIC/'authorize-local-review-history-available.json').read_bytes()==old
    current=e.read(c.PUBLIC/'authorize-local-review.json');receipt=e.read(c.PUBLIC/'authorize-local-review-replacement.json')
    assert current['review']['current_grants'][0]['state']=='expired'
    assert receipt['old_sha256']==m['old_public_review']['sha256']
    assert receipt['new_sha256']==e.sha(c.PUBLIC/'authorize-local-review.json')
    assert receipt['grant_issued'] is False and receipt['model_admissions']==0

@pytest.mark.parametrize('change',['still_available','used','different_grant','different_scope'])
def test_clock_alone_never_authorizes_expired_publication(tmp_path,monkeypatch,change):
    c,m=fixture(tmp_path,monkeypatch);old=Path(m['old_public_review']['path']).read_bytes();value=new_result(m)
    if change=='still_available':value['review']['current_grants'][0]['state']='available';value['review']['can_issue']=False
    if change=='used':value['review']['current_grants'][0]['used_executions']=1
    if change=='different_grant':value['review']['current_grants'][0]['grant_id']='different'
    if change=='different_scope':value['review']['scope']['workspace_id']='different'
    with pytest.raises((ValueError,driver_common.Refused)):e.publisher(c,m,'a'*64,original_driver())(c,'authorize-local-review.json',value)
    assert Path(m['old_public_review']['path']).read_bytes()==old

def test_failed_atomic_replace_leaves_first_evidence_unchanged(tmp_path,monkeypatch):
    c,m=fixture(tmp_path,monkeypatch);old=Path(m['old_public_review']['path']).read_bytes()
    monkeypatch.setattr(e.os,'replace',lambda *a:(_ for _ in ()).throw(OSError('synthetic atomic replacement failure')))
    with pytest.raises(OSError):e.publisher(c,m,'a'*64,original_driver())(c,'authorize-local-review.json',new_result(m))
    assert Path(m['old_public_review']['path']).read_bytes()==old
    assert (c.PUBLIC/'authorize-local-review-history-available.json').read_bytes()==old
    assert not (c.PUBLIC/'authorize-local-review-replacement.json').exists()

def test_installed_canonical_review_replaces_pending_review_without_issue():
    from okto_nexus.application.terminal_authorization import TerminalAuthorization
    old=e.read(M['old_public_review']['path'])['review'];calls=[];saved=[]
    class Flow(TerminalAuthorization):
        document={'authorization':{'state':'review','review':deepcopy(old),'review_revision':old['review_revision']}}
        def binding(self):return {'binding_id':old['scope']['binding_id']}
        def api(self,method,path,body):
            calls.append((method,path,body));return {'scope':old['scope'],'canonical':'new-review'}
        def _check_scope(self,scope,binding):assert scope==old['scope']
        def _save(self):saved.append(deepcopy(self.document))
        def authorize(self,**kwargs):pytest.fail('issuance/recovery must not be called')
    flow=Flow();result=flow.authorization_review(minutes=60,max_executions=20)
    assert [(m,p) for m,p,b in calls]==[('POST','/connections/authorizations:review')]
    assert calls[0][2]['minutes']==60 and calls[0][2]['max_executions']==20
    assert saved[0]['authorization']['state']=='review' and result['canonical']=='new-review'

def test_execute_copy_changes_only_explicit_pending_guard():
    source=Path(M['original_authorize']['path']).read_text()
    assert Path(M['execute_copy']['path']).read_text()==source.replace("require(pending is None, 'PRIOR_AUTHORIZATION_SELECTION_PRESENT')",'validate_retained_pending(context, pending)')
