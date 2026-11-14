"""GET-only exact owned request projection; excludes command text, outputs and credentials."""
from pathlib import Path
import hashlib,json,sys,time
from urllib.parse import urlencode,quote
HERE=Path(__file__).resolve().parent
BASE=Path('C:/Users/jpamb/AppData/Local/Temp/m1-v12-bundle-bldo9qy7/successor14/work-request12-package2')
assert Path(sys.prefix)==BASE/'package/venv'
sys.path.insert(0,str(BASE))
from cohort import Process
from okto_nexus.adapters.outbound.terminal_http import LocalOperatorHTTP
record=json.loads((BASE/'private/controller.json').read_bytes())['requests']['m1v14-local-work-12']
selected=json.loads((BASE/'public/nexus-owner-selection.json').read_bytes())
http=LocalOperatorHTTP(host='127.0.0.1',port=58631,timeout=10)
prefix='/api/v1/runtime-management';calls=[]
def get(path):
    calls.append(path);return http('GET',path)
handles=[]
try:
    for role in ('parent','launcher','child'):
        identity=selected['cohort'][role];h=Process(identity['pid']);handles.append(h)
        assert h.birth==identity['birth'] and not h.exited()
    service=get('/api/v1/service')['data']
    assert all(service.get(k)==selected[k] for k in ('pid','generation','instance_id'))
    session=get(prefix+'/runtime/sessions/'+record['session']+'?executor_id='+record['scope']['executor_id'])
    operation=get(prefix+'/runtime/operations/'+record['operation'])
    assert session['scope']==operation['scope'] and all(session['scope'][k]==v for k,v in record['scope'].items())
    assert operation['operation_id']==record['operation']
    approvals=get('/api/v1/approvals?'+urlencode({'workspace':record['scope']['workspace_id'],'status':'pending','offset':0,'limit':100}))['data']['items']
    items=[]
    for row in approvals:
        detail=get('/api/v1/approvals/'+quote(row['approval_id'],safe=''))['data']
        proposal=detail.get('request_payload',{}).get('kwargs',{});key=proposal.get('approval_key',{})
        if key.get('session_id')==record['session']:
            items.append({'approval_id':row['approval_id'],'status':detail.get('status'),'approval_key':key,
                'request_type':proposal.get('request_type'),'command_text_exported':False})
    value={'status':'EXACT_GET_OBSERVATION','service':{k:service.get(k) for k in ('pid','generation','instance_id','state','ready_for_queries')},
        'session':{k:session.get(k) for k in ('scope','lifecycle_state','lease_state','revision')},
        'operation':{k:operation.get(k) for k in ('scope','operation_id','action','admission_state','executor_stage','receipt_revision','possible_effect','retry_safe')},
        'pending_approvals':items,'approval_page_full':len(approvals)==100,'calls':calls,'post_count':0,
        'observed_at':time.time(),'controller_sha256':hashlib.sha256((BASE/'private/controller.json').read_bytes()).hexdigest()}
    with (HERE/'observation.json').open('x',encoding='utf-8') as out:json.dump(value,out,indent=2)
    print(json.dumps(value))
finally:
    for h in handles:h.close()
