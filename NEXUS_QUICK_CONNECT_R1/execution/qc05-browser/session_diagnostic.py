"""Offline read-only inspection of the preserved own fixture DB, never secrets."""
import hashlib
import json
from pathlib import Path
import sqlite3

HERE = Path(__file__).resolve().parent
ready = json.loads((HERE/'ready.json').read_text(encoding='utf-8'))
final = json.loads((HERE/'final.json').read_text(encoding='utf-8'))
home = Path(ready['home']).resolve()
assert home.parent == Path('C:/Users/jpamb/AppData/Local/Temp').resolve()
assert home.name.startswith('nexus-qc05-browser-')
databases = [p for p in home.rglob('nexus.db') if p.resolve().is_relative_to(home)]
assert len(databases) == 1
conn = sqlite3.connect(databases[0].as_uri() + '?mode=ro', uri=True)
conn.row_factory = sqlite3.Row
try:
    rows = [dict(row) for row in conn.execute('SELECT * FROM execution_sessions ORDER BY rowid')]
    allowed = {'session_id','binding_id','workspace_id','lifecycle_state','lease_state','stream_epoch',
               'created_at','updated_at','last_activity_at','last_seen_at','closed_at'}
    report = dict(db=str(databases[0]), mode='read-only; no query writes',
        before_evidence='Only whole-table count/hash was captured, not rows or per-column hashes.',
        changed_columns='UNKNOWN; exact changed columns and cause cannot be proved from whole-table digest.',
        after_metadata=[{k:v for k,v in row.items() if k in allowed} for row in rows],
        after_column_hashes={key:hashlib.sha256(json.dumps([row[key] for row in rows],sort_keys=True,
                                                        default=str).encode()).hexdigest() for key in rows[0]},
        seed_known_historical_fields={'session_id':'ui-session-2','lifecycle_state':'CLOSED',
                                     'lease_state':'CLOSED','stream_epoch':'ui-historical-epoch'},
        limitation='No claim that every Home GET was free of canonical maintenance effects. Eight protected tables remained byte equal; all nine row counts remained equal.')
    offline_hash = hashlib.sha256(json.dumps([list(row.values()) for row in rows],
                                             sort_keys=True, default=str).encode()).hexdigest()
    report['offline_after_lifespan_hash'] = offline_hash
    report['same_as_pre_lifespan_final_snapshot'] = offline_hash == final['after']['execution_sessions']['sha256']
    # The fixture applies a lease (ACTIVE) before yielding its source scenario.
    # Test exactly that one source-backed prior value, without modifying SQLite.
    candidate = [dict(row) for row in rows]
    selected = next(row for row in candidate if row['session_id'] == ready['identities']['question_session'])
    observed = selected['lease_state']
    selected['lease_state'] = 'ACTIVE'
    reconstructed = hashlib.sha256(json.dumps([list(row.values()) for row in candidate],
                                              sort_keys=True, default=str).encode()).hexdigest()
    report['single_column_source_hypothesis'] = dict(column='lease_state', before='ACTIVE', after=observed,
        reconstructed_sha256=reconstructed, original_sha256=ready['before']['execution_sessions']['sha256'],
        exact_whole_table_hash_match=reconstructed == ready['before']['execution_sessions']['sha256'])
    if report['single_column_source_hypothesis']['exact_whole_table_hash_match']:
        report['changed_columns'] = ['lease_state']
        report['proved_delta'] = dict(session_id=selected['session_id'], before='ACTIVE', after=observed,
            proof='Replacing only this one value in in-memory final rows reproduces the complete original table SHA256. No DB write.')
        report['cause'] = 'Not established; no claim of timestamp-only or perfectly passive Home GET.'
finally:
    conn.close()
(HERE/'session-diagnostic.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps(dict(sessions=len(rows),changed_columns=report['changed_columns'])))
