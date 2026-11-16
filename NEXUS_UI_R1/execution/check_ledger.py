"""Check UI-R1 bookkeeping, not product acceptance or campaign results."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT/'NEXUS_UI_R1'


def main():
    original = json.loads((PACKAGE/'execution/input-ledger.json').read_bytes())
    ledger = json.loads((PACKAGE/'NEXUS_UI_EXECUTION_LEDGER_R1.json').read_bytes())
    manifest = json.loads((PACKAGE/'MANIFESTO.json').read_bytes())
    for item in manifest['files']:
        path = PACKAGE/item['name']
        if item['name'] == 'NEXUS_UI_EXECUTION_LEDGER_R1.json':
            path = PACKAGE/'execution/input-ledger.json'
        assert hashlib.sha256(path.read_bytes()).hexdigest() == item['sha256'], path
    for field, count in [('tasks', 47), ('tests', 145), ('requirements', 18), ('prs', 9)]:
        current = {item['id']: item for item in ledger[field]}
        before = {item['id']: item for item in original[field]}
        assert len(current) == len(ledger[field]) == count
        assert current.keys() == before.keys(), field
        for key, item in before.items():
            # Execution may add fields but must preserve the supplied specification.
            for name, value in item.items():
                if name not in {'status', 'evidence', 'limitations'}:
                    assert current[key][name] == value, (field, key, name)
    tasks = {item['id']: item for item in ledger['tasks']}
    tests = {item['id']: item for item in ledger['tests']}
    for key, task in tasks.items():
        assert task['status'] in {'TODO', 'IN_PROGRESS', 'IMPLEMENTED', 'VERIFIED', 'BLOCKED'}
        assert set(task['depends_on']) <= tasks.keys()
        assert set(task['test_ids']) <= tests.keys()
        if task['status'] == 'VERIFIED':
            assert task['evidence'], key
    for test in tests.values():
        assert test['status'] in {'NOT_RUN', 'PASS', 'FAIL', 'BLOCKED'}
        assert set(test['tasks']) <= tasks.keys()
        if test['status'] == 'PASS':
            assert test['evidence'], test['id']
    visited, active = set(), set()

    def visit(key):
        assert key not in active, ('dependency cycle', key)
        if key in visited:
            return
        active.add(key)
        for dep in tasks[key]['depends_on']:
            visit(dep)
        active.remove(key)
        visited.add(key)

    for key in tasks:
        visit(key)
    print('UI-R1:47 tasks,145 scenarios,18 requirements,9 PRs; inputs/IDs/specification/DAG valid.')
    print('Bookkeeping only: no product, browser, screen-reader or harness certification.')


if __name__ == '__main__':
    main()
