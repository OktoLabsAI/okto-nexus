"""Post-exit, query-only metadata projection; no service or provider calls."""
import hashlib
import json
import sqlite3
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
B = Path('C:/Users/jpamb/AppData/Local/Temp/m1-v12-bundle-bldo9qy7')
SESSION = 'ses_abdc7fd9ab15ccadc06fe7aec6b9f247'
EXECUTOR = 'exe_429348b4147e50ab63d19caa4cd2255c'

def observe():
    path = B/'campaign/nexus-home/core-runtime'/('session-'+hashlib.sha256((EXECUTOR+'\0'+SESSION).encode()).hexdigest()+'.db')
    db = sqlite3.connect(path.as_uri()+'?mode=ro', uri=True, timeout=2)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA query_only=ON')
    try:
        result = {'launch': [dict(r) for r in db.execute('SELECT server_id,executor_id,session_id,opening_operation_id,connection_generation,owner_generation,revision,spawn_claimed,producer_fenced,stop_proof FROM process_launches WHERE session_id=?', (SESSION,))],
                  'counts': {t: db.execute('SELECT count(*) FROM '+t+' WHERE session_id=?', (SESSION,)).fetchone()[0] for t in ('process_births','events','event_streams')},
                  'table_names': [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]}
        result['action_counts'] = [dict(r) for r in db.execute('SELECT a.action,count(*) AS count FROM operation_actions a JOIN operations_v2 o USING(server_id,executor_id,operation_id) WHERE o.session_id=? GROUP BY a.action', (SESSION,))]
        result['operations'] = [dict(r) for r in db.execute('SELECT operation_id,stage,possible_effect,retry_safe,native_id,error_code FROM operations_v2 WHERE session_id=?', (SESSION,))]
        result['slots'] = [dict(r) for r in db.execute('SELECT operation_id,released FROM owned_slot_reservations WHERE session_id=?', (SESSION,))]
        result['claims'] = [dict(r) for r in db.execute('SELECT operation_id,reconciliation_pending FROM session_claims WHERE session_id=?', (SESSION,))]
        result.pop('table_names')
    finally:
        db.close()
    db = sqlite3.connect((B/'campaign/nexus-home/nexus.db').as_uri()+'?mode=ro', uri=True, timeout=2)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA query_only=ON')
    try:
        result['canonical_session'] = dict(db.execute('SELECT session_id,lifecycle_state,lease_state,owner_generation,stream_epoch FROM execution_sessions WHERE session_id=?', (SESSION,)).fetchone())
        result['canonical_receipts'] = [dict(r) for r in db.execute('SELECT operation_id,stage,error_code,possible_effect,retry_safe,receipt_revision FROM execution_receipts WHERE operation_id IN (?,?) ORDER BY operation_id,receipt_revision', ('op_c43b1ade4ad6cd29dd60bf4eb1970fba','op_dcd0455d4820f9abd40a57fad32c8fa9'))]
    finally:
        db.close()
    result['observed_at'] = time.time()
    result['method'] = {'mode':'ro','query_only':True,'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'scope':'Exact request11 Core session and two canonical receipt IDs; no payload/body/auth columns.'}
    return result

def main():
    result = observe()
    with (HERE/'post-exit-accounting-observation.json').open('x',encoding='utf-8',newline='\n') as out:
        json.dump(result,out,indent=2);out.write('\n')
    print(json.dumps(result,indent=2))

if __name__ == '__main__': main()
