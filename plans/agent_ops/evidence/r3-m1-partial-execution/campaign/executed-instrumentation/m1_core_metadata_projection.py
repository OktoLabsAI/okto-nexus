from pathlib import Path
import json,sqlite3
root=Path('C:/Users/jpamb/AppData/Local/Temp/r3-campaign-refresh-0ssbo8pb/m1-campaign')
core=root/'nexus-home/core-runtime/session-ef244ce98fccbe3be1dc54013ba7dc75abcde017ba84fcc06c29438903cefd99.db'
with sqlite3.connect(core.as_uri()+'?mode=ro',uri=True) as db:
    db.execute('PRAGMA query_only=ON')
    result={}
    queries={
        'session_claims':'SELECT server_id,executor_id,session_id,operation_id,reconciliation_pending,release_id,release_digest FROM session_claims',
        'streams':'SELECT server_id,executor_id,session_id,stream_epoch,next_sequence,acked_sequence,compacted_sequence FROM event_streams',
        'operations':'SELECT server_id,executor_id,session_id,operation_id,stage,possible_effect,retry_safe,error_code FROM operations_v2'}
    for name,sql in queries.items():
        cursor=db.execute(sql)
        result[name]=[dict(zip([c[0] for c in cursor.description],row)) for row in cursor]
result['server_python']='C:/Users/jpamb/AppData/Local/Temp/r3-campaign-refresh-0ssbo8pb/native/venv/Scripts/pythonw.exe'
result['server_site_packages']='C:/Users/jpamb/AppData/Local/Temp/r3-campaign-refresh-0ssbo8pb/native/venv/Lib/site-packages'
result['historical_pins']={'nexus_wheel':'cd1653dbdb48031e6c04771889ecc3efa5de965973dfe29026436fe263b478ad','core_wheel':'1407014ea12f7e6f04ac70b9da8dbf8ebd9a57d8021bb5e74437bc22bd274f7a'}
result['note']='Read-only fixed columns; no event bodies or private native transcript/config. Process STOPPED/core_release_pending false came from GET service, not this claim schema.'
(root/'public/core-reconciliation-metadata.json').write_text(json.dumps(result,indent=2))
state=json.loads((root/'private/controller.json').read_text())
c=state['collector']['state']
coverage={'private_faults':state['faults'],'global_reserved_requests':len(state['requests']),
          'setup_high_water':state['requests']['m1-local-setup']['monitor']['high_water'],
          'streams':{k:{f:v[f] for f in ('scope','epoch','cursor','watermark','gap','page_seen','retired','thread')} for k,v in c['streams'].items()},
          'turns':{k:{f:v[f] for f in ('operation_id','stream','started','terminal','usage_seen','thread','turn_id')} for k,v in c['turns'].items()},
          'threads':{k:{f:v[f] for f in ('high_water','baseline','baseline_basis','native_thread_id','owner_stream')} for k,v in c['threads'].items()},
          'replaces_projection_only':'final-accounting-coverage.json used absent field names baseline_total/native_thread_id for two projections; retained as history, no checkpoint change.',
          'final_billed_atomic_usage':False}
coverage['known_observed_minimum']=coverage['setup_high_water']+sum(v['high_water']-v['baseline'] for v in c['threads'].values())
(root/'public/final-accounting-coverage-v2.json').write_text(json.dumps(coverage,indent=2))
print(json.dumps(result))
