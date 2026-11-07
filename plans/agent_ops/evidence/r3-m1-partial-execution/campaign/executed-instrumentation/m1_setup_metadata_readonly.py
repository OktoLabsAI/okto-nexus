from pathlib import Path
import json,sqlite3
root=Path('C:/Users/jpamb/AppData/Local/Temp/r3-campaign-refresh-0ssbo8pb/m1-campaign')
record=json.loads((root/'public/local-setup-result.json').read_text())
journal=Path(record['monitor']['journal'])
assert journal.resolve().is_relative_to((root/'nexus-home/connection-tests').resolve())
fields=('$.payload.model','$.payload.modelProvider','$.payload.approvalPolicy','$.payload.sandbox',
        '$.payload.thread.model','$.payload.thread.modelProvider','$.payload.thread.approvalPolicy','$.payload.thread.sandbox')
with sqlite3.connect(journal.as_uri()+'?mode=ro',uri=True) as db:
    db.execute('PRAGMA query_only=ON')
    methods=[{'native_type':r[0],'events':r[1]} for r in db.execute("SELECT json_extract(body,'$.native_type'),count(*) FROM events GROUP BY json_extract(body,'$.native_type') ORDER BY 1")]
    observed={}
    for field in fields:
        rows=db.execute('SELECT DISTINCT json_extract(body,?) FROM events WHERE json_type(body,?) = ?', (field,field,'text')).fetchall()
        observed[field]=[r[0] for r in rows if isinstance(r[0],str) and len(r[0])<=256]
report={'source':'owned standalone setup journal fixed metadata projections only','native_methods':methods,
        'reported_native_policy_fields':observed,'missing_fields_mean':'not reported in this event projection, not inferred from personal configuration',
        'personal_config_read':False,'instructions_or_transcripts_collected':False}
(root/'public/setup-native-metadata.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report))
