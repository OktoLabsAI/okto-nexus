import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
records = json.loads((HERE.parent / 'persistence-applied-final/report.json').read_text(encoding='utf-8'))['records']
for row in records:
    target = REPO / row['target']
    backup = HERE / 'before' / target.name
    if backup.exists():
        target.write_bytes(backup.read_bytes())
    assert hashlib.sha256(target.read_bytes()).hexdigest() == row['persisted_sha256']
for name in ['apply.py', 'finish.py']:
    path = HERE / name
    path.write_text(path.read_text(encoding='utf-8').replace('.read_text()', ".read_text(encoding='utf-8')"), encoding='utf-8')
print('Exact 22-file persistence baseline restored; scripts use explicit UTF-8.')
