from pathlib import Path
import json,sqlite3
root=Path('C:/Users/jpamb/AppData/Local/Temp/r3-campaign-refresh-0ssbo8pb/m1-campaign')
home=root/'nexus-home'
scope=('srv_5a02d4e235c6f532d56f1009516c9f6b','exe_73883c04aeca5110dd9212baff8c08a1','ses_e8ddc66adc041a490d97a2419778e90c')
result={}
def project(path,queries):
    with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True) as db:
        db.execute('PRAGMA query_only=ON')
        for key,sql,args in queries:
            cursor=db.execute(sql,args)
            result[key]=[dict(zip([c[0] for c in cursor.description],r)) for r in cursor]
project(home/'core-runtime/session-ef244ce98fccbe3be1dc54013ba7dc75abcde017ba84fcc06c29438903cefd99.db',[
    ('session_open_generations','SELECT server_id,executor_id,session_id,operation_id,connection_generation,owner_generation FROM session_open_generations WHERE server_id=? AND executor_id=? AND session_id=?',scope),
    ('operation_actions','SELECT server_id,executor_id,operation_id,action,terminal_event_expected FROM operation_actions WHERE server_id=? AND executor_id=?',scope[:2])])
project(home/'nexus.db',[
    ('execution_sessions','SELECT server_id,executor_id,session_id,owner_generation,open_operation_id,stream_epoch,lifecycle_state FROM execution_sessions WHERE server_id=? AND executor_id=? AND session_id=?',scope),
    ('execution_operations',"SELECT server_id,executor_id,session_id,operation_id,action,admission_state,json_extract(expected_revisions_json,'$.session_owner_generation') AS expected_session_owner_generation FROM execution_operations WHERE server_id=? AND executor_id=? AND session_id=?",scope)])
result['read_only']=True
(root/'public/generation-reconciliation-metadata.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result))
