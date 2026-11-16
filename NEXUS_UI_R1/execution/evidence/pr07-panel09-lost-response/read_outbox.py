from pathlib import Path
import json
import sqlite3
p=Path(__file__).resolve().parent
home=Path(json.loads((p/'ready.json').read_text())['home'])
c=sqlite3.connect((home/'home/nexus.db').as_uri()+'?mode=ro',uri=True)
c.row_factory=sqlite3.Row
tables=[r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%outbox%'")]
result={}
for table in tables:
    columns=[r[1] for r in c.execute('PRAGMA table_info('+table+')')]
    if 'operation_id' in columns:
        result[table]=c.execute("SELECT COUNT(*) FROM "+table+" WHERE operation_id='r4op_389ba237bed71382153abfc7f5a45f38'").fetchone()[0]
c.close()
(p/'exact-outbox.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
