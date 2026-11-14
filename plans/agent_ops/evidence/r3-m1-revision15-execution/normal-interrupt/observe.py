"""Bounded GET-only exact request13 projection; no commands/auth/transcripts exported."""
from pathlib import Path
import hashlib,json,sys,time
HERE=Path(__file__).resolve().parent
BASE=Path('C:/Users/jpamb/AppData/Local/Temp/m1-v12-bundle-bldo9qy7/successor14/work-revision15')
assert Path(sys.prefix)==BASE/'package/venv'
sys.path.insert(0,str(BASE))
from cohort import Process
from okto_nexus.adapters.outbound.terminal_http import LocalOperatorHTTP
selected=json.loads((BASE/'public/nexus-owner-selection.json').read_bytes())
assert selected['pid']==11748 and selected['generation']=='000516de38262af8bdf99dee1c5271bc'
http=LocalOperatorHTTP(host='127.0.0.1',port=58631,timeout=5)
prefix='/api/v1/runtime-management';calls=[];started=time.monotonic()
def get(path):
    assert time.monotonic()-started<30
    calls.append(path);value=http('GET',path)
    assert time.monotonic()-started<30
    return value
handles=[]
try:
    for role in ('parent','launcher','child'):
        identity=selected['cohort'][role];h=Process(identity['pid']);handles.append(h)
        assert h.birth==identity['birth'] and not h.exited()
    service=get('/api/v1/service')['data']
    assert all(service.get(k)==selected[k] for k in ('pid','generation','instance_id'))
    operation=get(prefix+'/runtime/operations/op_d7ee27186ba720011a5c3704196eab09')
    scope=operation['scope'];assert scope['session_id']=='ses_86bf8a7f016fafe06e794ce5f0028611'
    session=get(prefix+'/runtime/sessions/'+scope['session_id']+'?executor_id='+scope['executor_id'])
    assert session['scope']==scope
    detail=get('/api/v1/approvals/r4request_e133588fe9c28d66ac53353d1fedbde4f26e5c4607e382226d013500f0ad48c7')['data']
    proposal=detail.get('request_payload',{}).get('kwargs',{});key=proposal.get('approval_key',{})
    assert key.get('session_id')==scope['session_id']
    value={'status':'EXACT_GET_ONLY_OBSERVATION','service':{k:service.get(k) for k in ('pid','generation','instance_id','state','ready_for_queries')},
        'session':{k:session.get(k) for k in ('scope','lifecycle_state','lease_state','revision')},
        'operation':{k:operation.get(k) for k in ('scope','operation_id','action','admission_state','executor_stage','receipt_revision','possible_effect','retry_safe')},
        'approval':{'approval_id':detail.get('approval_id'),'status':detail.get('status'),'approval_key':key,'command_text_exported':False},
        'calls':calls,'post_count':0,'observed_at':time.time(),'controller_concurrent_snapshot_sha256':hashlib.sha256((BASE/'private/controller.json').read_bytes()).hexdigest(),
        'controller_may_continue_observation':True}
    with (HERE/'observation.json').open('x',encoding='utf-8') as out:json.dump(value,out,indent=2)
    print(json.dumps(value))
finally:
    for h in handles:h.close()
