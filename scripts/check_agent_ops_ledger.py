"""Check scope coverage and evidence references; does not certify product behavior."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    ledger = json.loads((ROOT / 'plans/agent_ops/ledger.json').read_text(encoding='utf-8'))
    plan = ROOT / ledger['plan']
    source = plan.read_text(encoding='utf-8')
    assert hashlib.sha256(source.encode('utf-8')).hexdigest() == ledger['plan_sha256'], 'Plan changed; reconcile explicitly'
    expected = {
        'tasks': set(re.findall(r'^\*\*((?:BASE|SVC|DX|ATN|OBS)-\d+) ', source, re.M)),
        'scenarios': set(re.findall(r'^\| ((?:SVC-T|DX-T|AT-|OB-|RG-)\d+) \|', source, re.M)),
        'invariants': set(re.findall(r'^\| (INV-\d+) \|', source, re.M)),
        'completion_criteria': {f'AC-{int(n):02}' for n in re.findall(r'^(\d+)\. ', source.split('# 17.')[1].split('# 18.')[0], re.M)},
    }
    for section, ids in expected.items():
        assert set(ledger[section]) == ids, (section, ids.symmetric_difference(ledger[section]))
    literal = {
        'tasks': dict(re.findall(r'^\*\*((?:BASE|SVC|DX|ATN|OBS)-\d+) — (.*?)\.\*\*', source, re.M)),
        'scenarios': dict(re.findall(r'^\| ((?:SVC-T|DX-T|AT-|OB-|RG-)\d+) \| (.*?) \|$', source, re.M)),
        'invariants': dict(re.findall(r'^\| (INV-\d+) \| (.*?) \|$', source, re.M)),
        'completion_criteria': {
            f'AC-{int(n):02}': text
            for n, text in re.findall(r'^(\d+)\. (.+)$', source.split('# 17.')[1].split('# 18.')[0], re.M)
        },
    }
    for section, rows in literal.items():
        assert set(rows) == expected[section], (section, 'Literal extraction differs from fixed ID inventory')
        field = 'title' if section == 'tasks' else 'requirement'
        for key, text in rows.items():
            assert ledger[section][key][field] == text, (key, 'Ledger text differs from the fixed plan')
    for key, task in ledger['tasks'].items():
        assert task['status'] in {'NOT_STARTED', 'IN_PROGRESS', 'IMPLEMENTED', 'VERIFIED', 'BLOCKED'}, key
        if task['status'] == 'VERIFIED':
            assert task['files'] and task['tests'] and task['result'] and task['platform'], key
            for filename in task['files']:
                assert (ROOT / filename).is_file(), (key, filename)
    for section in ('scenarios', 'invariants', 'completion_criteria', 'milestones'):
        for key, item in ledger[section].items():
            if item['status'] == 'VERIFIED':
                assert item['evidence'], key
                for filename in item['evidence']:
                    assert (ROOT / filename).is_file(), (key, filename)
    print(', '.join(f'{len(ids)} {name}' for name, ids in expected.items()))
    print('Titles and requirements match the fixed plan literally.')
    print('Scope coverage valid. This check is not implementation or campaign acceptance.')


if __name__ == '__main__':
    main()
