"""Check execution annotations without letting the supplied QC specification drift."""
import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'NEXUS_QUICK_CONNECT_R1'


def main():
    original = json.loads((BASE / 'input/NEXUS_QUICK_CONNECT_LEDGER_R1.json').read_text('utf-8'))
    current = json.loads((BASE / 'NEXUS_QUICK_CONNECT_LEDGER_R1.json').read_text('utf-8'))
    stripped = copy.deepcopy(current)
    stripped.pop('execution', None)
    for group, states in (
        ('tasks', {'TODO', 'IN_PROGRESS', 'IMPLEMENTED', 'VERIFIED', 'BLOCKED'}),
        ('tests', {'NOT_RUN', 'PASS', 'FAIL', 'BLOCKED'}),
        ('requirements', {'NOT_VERIFIED', 'PARTIAL', 'VERIFIED', 'BLOCKED'}),
    ):
        expected = {row['id']: row for row in original[group]}
        for row in stripped[group]:
            source = expected[row['id']]
            assert row['status'] in states, (row['id'], row['status'])
            evidence = row.get('evidence', [])
            if row['status'] in {'PASS', 'VERIFIED', 'IMPLEMENTED'}:
                assert evidence, ('missing evidence', row['id'])
            for item in evidence:
                path = BASE / item['path']
                assert path.is_relative_to(BASE) and path.is_file(), ('missing evidence file', row['id'], path)
                assert item.get('scope') and item.get('commit'), ('missing evidence scope/commit', row['id'])
            row['status'] = source['status']
            if 'evidence' in source:
                row['evidence'] = source['evidence']
            else:
                row.pop('evidence', None)
            row.pop('execution_notes', None)
    assert stripped == original, 'Normative specification drift'
    print(json.dumps({'status': 'PASS', 'scope': 'execution_ledger_integrity_only',
        'counts': {group: {state: sum(row['status'] == state for row in current[group])
            for state in sorted({row['status'] for row in current[group]})}
            for group in ('tasks', 'tests', 'requirements')}}, indent=2))


if __name__ == '__main__':
    main()
