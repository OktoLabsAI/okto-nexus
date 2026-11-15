"""Own session metadata only, no native command/tool content or credentials."""
from pathlib import Path
import collections
import hashlib
import json
import sqlite3

HERE=Path(__file__).resolve().parent
BASE=Path('C:/Users/jpamb/AppData/Local/Temp/m1-v12-bundle-bldo9qy7')
R=Path('C:/Users/jpamb/AppData/Local/Temp/sonnet-canonical-recovery-proposal-7oq808_t')
U=Path('C:/Users/jpamb/AppData/Local/Temp/m1-sonnet-remote-candidate-2c_4af0t/successor02')
db=BASE/'campaign/connector-state/executor-journal.db'
session='ses_b8b6cbd6ec8f9cb75d667276f5422c44'
operation='op_423345383752a6d0b8095d73159d1257'
with sqlite3.connect(db.as_uri()+'?mode=ro',uri=True) as c:
    c.execute('pragma query_only=on')
    rows=c.execute('select sequence,body from events where server_id=? and executor_id=? and session_id=? order by sequence',
        ('srv_a3f134b449dbffa20c126dae6f9a8aa9','exe_ac3fd8f5f8a35aaf344bb8aebd13be4e',session)).fetchall()
events=[json.loads(body) for _,body in rows]
def pin(path):return {'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
def bodypin(index):
    body=rows[index][1]
    return hashlib.sha256(body if isinstance(body,bytes) else body.encode()).hexdigest()
init=next(e for e in events if e['native_type']=='system:init')['payload']
refused=[(i,e) for i,e in enumerate(events) if e['native_type']=='unsupported_control_request']
assert len(refused)==1
index,event=refused[0];request=event['payload']['request']
terminal=next(e for e in events if e['native_type']=='result:success')
assert terminal['operation_id']==operation
usage=terminal['payload']['usage'];fields=('input_tokens','cache_read_input_tokens','cache_creation_input_tokens','output_tokens')
output=next(e for e in events if e['native_type']=='result:output')['payload']['output_text']+terminal['payload']['output_text']
tool_error=next(e for e in events if e['sequence']==110)['payload']['tool_use_result']
assert tool_error=='Error: Tool permission request failed: Error: Unsupported or stale native permission request'
report={
 'classification':'NATIVE_PERMISSION_TOOL_UNSUPPORTED_PRODUCT_COMPATIBILITY',
 'read_mode':'SQLite mode=ro/query_only; no service/provider/control calls',
 'scope':{k:event[k] for k in ('server_id','executor_id','session_id','stream_epoch')},
 'operation_id':operation,'event_count_at_read':len(events),
 'types':dict(collections.Counter(e['native_type'] for e in events)),
 'configuration':{'model':init['model'],'permissionMode':init['permissionMode'],'claude_code_version':init['claude_code_version'],
                  'PowerShell_advertised': 'PowerShell' in init['tools'],'Bash_advertised':'Bash' in init['tools']},
 'native_request':{'sequence':event['sequence'],'event_sha256':bodypin(index),
   'request_id':event['payload']['request_id'],'subtype':request['subtype'],'tool_name':request['tool_name'],
   'input_keys':sorted(request['input']),'tool_use_id':request['tool_use_id'],
   'command_sha256':hashlib.sha256(request['input']['command'].encode()).hexdigest(),
   'persistent_permission_suggestion_applied':False,'suggestion_present':bool(request.get('permission_suggestions'))},
 'native_tool_result':{'sequence':110,'is_error':True,'error':tool_error},
 'native_permission_requests_published':sum(e['native_type']=='control_request:can_use_tool' for e in events),
 'final_text':output,'native_terminal':{'sequence':terminal['sequence'],'type':terminal['native_type'],
    'delivery_phase':terminal['payload']['delivery_phase'],'delivery_outcome':terminal['payload']['delivery_outcome'],
    'permission_denials':len(terminal['payload'].get('permission_denials',[]))},
 'usage':{**{k:usage[k] for k in fields},'total':sum(usage[k] for k in fields),'prior_carried':36306,
          'campaign_total':36306+sum(usage[k] for k in fields)},
 'actual_result':pin(U/'paid-work/public/m1-sonnet-remote-useful-03-result.json'),
 'original_plan':pin(U/'work-plan.json'),
 'cause':'claude_permission_tool_supported rejects PowerShell (supported plain tools are Write/Edit/Bash/AskUserQuestion). Adapter sends an error control_response instead of a native approval; therefore no canonical human question was available.',
 'source':{
  'installed_validator':pin(R/'package/venv/Lib/site-packages/nexus_connector_core/native/native_inputs.py'),
  'installed_adapter':pin(R/'package/venv/Lib/site-packages/nexus_connector_core/native/adapters/claude_code_stream.py')},
 'correction_proposal':'Add explicit PowerShell native permission support, retaining normal request/decision validation, exact original input, current turn generation, human decision and no persistent permission update. Qualify actual 2.1.323 envelope offline before any later package or call.',
 'no_new_call_selected':True,'useful_result_confirmed':False,
}
(HERE/'diagnosis.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
allow={'files':[pin(HERE/'diagnose.py'),pin(HERE/'diagnosis.json')]}
(HERE/'public-allowlist.json').write_text(json.dumps(allow,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'diagnosis':pin(HERE/'diagnosis.json'),'allowlist':pin(HERE/'public-allowlist.json'), 'usage':report['usage']}))
