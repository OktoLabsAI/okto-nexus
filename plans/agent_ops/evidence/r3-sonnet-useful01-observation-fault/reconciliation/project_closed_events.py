"""Exact own closed stream; read-only SQLite, strict accounting projection."""
from pathlib import Path
import hashlib
import json
import sqlite3
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from sonnet_usage import project

db = Path('C:/Users/jpamb/AppData/Local/Temp/m1-v12-bundle-bldo9qy7/campaign/connector-state/executor-journal.db')
scope = dict(server_id='srv_a3f134b449dbffa20c126dae6f9a8aa9',
             executor_id='exe_ac3fd8f5f8a35aaf344bb8aebd13be4e',
             session_id='ses_e13d6e02f5ea6270004c5bf15e298e73',
             stream_epoch='stream_dbd162d29f87f5656c4f170e045c9846')
with sqlite3.connect(db.as_uri() + '?mode=ro', uri=True) as c:
    c.execute('pragma query_only=on')
    rows = c.execute('select sequence,body from events where server_id=? and executor_id=? and session_id=? and stream_epoch=? order by sequence', tuple(scope.values())).fetchall()
assert [r[0] for r in rows] == list(range(1, len(rows) + 1))
events = []
body_pins = []
for seq, body in rows:
    raw = json.loads(body)
    assert all(raw[k] == v for k, v in scope.items()) and raw['sequence'] == seq
    events.append(project(raw))
    body_pins.append({'sequence': seq, 'sha256': hashlib.sha256(body if isinstance(body,bytes) else body.encode()).hexdigest()})
def save(name, value):
    p = HERE / name
    p.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
    return hashlib.sha256(p.read_bytes()).hexdigest()
print(json.dumps({'projection_sha256': save('events-projected.json', events),
                  'source_sha256': save('event-source-pins.json', {'database': str(db), 'mode': 'ro/query_only', 'scope': scope, 'count':len(rows), 'events':body_pins})}))
