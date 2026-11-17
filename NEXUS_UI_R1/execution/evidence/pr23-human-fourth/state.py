from pathlib import Path
from datetime import datetime,timezone,timedelta
import hashlib
import json
import sqlite3

here=Path(__file__).resolve().parent
root=here.parents[3]
control=Path('C:/Users/jpamb/AppData/Local/Temp/nexus-ui043-fourth-control-0e3arciw')
ready=json.loads((control/'ready.json').read_text())
conn=sqlite3.connect((Path(ready['home'])/'home/nexus.db').as_uri()+'?mode=ro',uri=True)
conn.row_factory=sqlite3.Row
requests=[dict(r) for r in conn.execute('SELECT canonical_request_id,received_at,expires_at FROM execution_native_requests')]
conn.close()
state={'status':'VISIBLE_INITIAL_HOME_READY_AWAITING_HUMAN_TASK','url':ready['url'],'browser_session':'ui043-fourth-human','browser_pid':52712,'fixture_exec_session':56736,'fixture_pid':ready['fixture_pid'],
 'control_directory':str(control),'stop_file':str(control/'stop'),'extend_read_window_file':str(control/'extend-read-window.json'),
 'read_window_seconds':3600,'read_window_deadline_approx_from_ready_file':(datetime.fromtimestamp((control/'ready.json').stat().st_mtime,timezone.utc)+timedelta(seconds=3600)).isoformat(),
 'extension_format':{'request_id':'unique explicit facilitator ID','seconds':'1..3600 before expiry; total2hours maximum'},
 'extension_scope':'Observation only; never renews original grant/ticket or request120sTTL.',
 'original_authority_expiries':ready['decision_authority_times'],'original_grants':ready['original_grants'],'initial_native_requests':requests,
 'fresh_question_trigger_used':False,'human_window_operated_after_handoff':False,'tasks_performed_by_agent':False,
 'project_root':ready['identities']['project_root'],'project_label':'Sample project','workspace_id':'ws',
 'baseline_catalog_limit':'Both canonical connections belong to subject/Codex on the same unnamed Connector host; exact binding/session identities differ but display labels are not distinct. Root notified before handoff; no authority/DTO altered.',
 'provider_calls':0,'native_binary_calls':0,'personal_auth':False,'cleanup':'Pending end of human handoff or finite observation deadline; do not close active human form automatically.'}
(here/'runtime-state.json').write_text(json.dumps(state,indent=2),encoding='utf-8')
pins={str(p.relative_to(here)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in here.rglob('*') if p.is_file() and p.name!='manifest.json' and '__pycache__' not in p.parts}
(here/'manifest.json').write_text(json.dumps(pins,indent=2),encoding='utf-8')
print(json.dumps({'entries':len(pins),'initial_native_requests':requests,'read_window_deadline_approx':state['read_window_deadline_approx_from_ready_file']}))
