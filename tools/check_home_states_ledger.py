"""Check HOME-STATES execution annotations without changing its specification."""
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path

BASE = Path(__file__).resolve().parents[1] / 'NEXUS_HOME_ESTADOS_R1'


def main():
    original = json.loads((BASE / 'input/NEXUS_HOME_ESTADOS_LEDGER_R1.json').read_text('utf-8'))
    current = json.loads((BASE / 'NEXUS_HOME_ESTADOS_LEDGER_R1.json').read_text('utf-8'))
    stripped = deepcopy(current)
    stripped.pop('execution', None)
    for group, states in (
        ('tasks', set(original['task_statuses'])),
        ('stages', set(original['task_statuses'])),
        ('tests', set(original['test_statuses'])),
        ('requirements', {'NOT_VERIFIED', 'PARTIAL', 'VERIFIED', 'BLOCKED'}),
    ):
        expected = {row['id']: row for row in original[group]}
        for row in stripped[group]:
            source = expected[row['id']]
            assert row.get('status', 'NOT_VERIFIED') in states, row['id']
            for item in row.get('evidence', []):
                path = (BASE / item['artifact_path']).resolve()
                assert path.is_relative_to(BASE.resolve()) and path.is_file(), item
                assert all(item.get(key) is not None for key in original['evidence_requirements']), item
            if row.get('status') in ('VERIFIED', 'IMPLEMENTED', 'PASS'):
                assert row.get('evidence'), row['id']
            for name in ('status', 'evidence', 'execution_notes'):
                if name in source:
                    row[name] = source[name]
                else:
                    row.pop(name, None)
    assert stripped == original, 'Normative specification drift'
    print(json.dumps(dict(status='PASS', scope='ledger_integrity_only', counts={
        group: dict(Counter(row.get('status', 'NOT_VERIFIED') for row in current[group]))
        for group in ('tasks', 'tests', 'stages', 'requirements')})))


if __name__ == '__main__':
    main()
