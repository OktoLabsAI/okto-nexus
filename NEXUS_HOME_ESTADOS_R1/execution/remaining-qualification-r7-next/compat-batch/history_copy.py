"""PREPARED old-producer immutable history snapshot/copy; no app import or SQL writes."""
import argparse
import hashlib
import json
import shutil
import sqlite3
from pathlib import Path

TABLES = ('execution_operations', 'execution_receipts', 'execution_native_requests',
    'execution_decisions', 'runtime_execution_grants', 'execution_bindings',
    'execution_domain_deliveries', 'execution_results')


def snapshot(home):
    with sqlite3.connect((home / 'nexus.db').as_uri() + '?mode=ro', uri=True) as conn:
        existing = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        values = {}
        for table in TABLES:
            if table not in existing:
                values[table] = {'present': False}
                continue
            columns = [row[1] for row in conn.execute('PRAGMA table_info(' + table + ')')]
            rows = conn.execute('SELECT * FROM ' + table + ' ORDER BY rowid').fetchall()
            raw = json.dumps(rows, ensure_ascii=False, separators=(',', ':'), default=lambda b:b.hex()).encode()
            values[table] = {'present': True, 'columns': columns, 'rows': len(rows),
                'sha256': hashlib.sha256(raw).hexdigest()}
        return values


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--gate', choices=['ROOT_APPROVED_COMPAT_BATCH'], required=True)
    parser.add_argument('--old-home', type=Path, required=True)
    parser.add_argument('--new-home', type=Path, required=True)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--old-stop-proof', type=Path, required=True)
    args = parser.parse_args()
    root, old, new = args.root.resolve(), args.old_home.resolve(), args.new_home.resolve()
    assert root.name.startswith('nexus-hst-compat-') and old.is_relative_to(root) and new.is_relative_to(root)
    proof = json.loads(args.old_stop_proof.read_text(encoding='utf-8'))
    assert proof['canonical_stop_state'] == 'stopped' and proof['physical_same_birth_remaining'] == 0
    assert proof['shutdown_outcome'] == 'drained'
    assert not new.exists(), 'Exactly one copy; refuse existing target'
    assert not any(path.is_symlink() for path in old.rglob('*'))
    before = snapshot(old)
    for table in ('execution_receipts', 'execution_native_requests', 'execution_decisions',
            'runtime_execution_grants', 'execution_results'):
        assert before[table]['present'] and before[table]['rows'] > 0, ('Missing actual old producer facts', table)
    shutil.copytree(old, new)
    assert snapshot(new) == before
    value = {'old': before, 'copied': snapshot(new), 'copy_count': 1,
        'old_info_sha256': proof['old_info_sha256'], 'old_offered_v2': proof['old_offered_v2'],
        'limits': 'Real old producer required before this helper. Schema migration may add tables; existing protected table rows/hashes must remain unchanged after R9 projection.'}
    assert value['old_offered_v2'] is False
    (root / 'control/history-copy.json').write_text(json.dumps(value, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
