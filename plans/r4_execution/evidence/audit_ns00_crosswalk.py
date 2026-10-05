import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

root = Path(__file__).resolve().parents[3]
paths = ['plans/07_RASTREABILIDADE_R3.md', 'plans/BACKLOG_R4.json',
         'plans/MATRIZ_TESTES_R4.json', 'plans/r4_execution/acceptance_inventory.json',
         'tests/execution_r4/test_ns00.py']
backlog = json.loads((root / paths[1]).read_text(encoding='utf-8'))
matrix = json.loads((root / paths[2]).read_text(encoding='utf-8'))
inventory = json.loads((root / paths[3]).read_text(encoding='utf-8'))
tasks = {row['id'] for row in backlog['tasks']}
crosswalk = (root / paths[0]).read_text(encoding='utf-8')
rows = re.findall(r'^\| (N\d{2}\.\d) \|.*\| (NS[^|]+) \|$', crosswalk, re.M)
mapping = {old: re.findall(r'NS\d{2}\.\d{2}', target) for old, target in rows}
expected = {f'N{section:02}.{item}' for section in range(14) for item in range(1, 6)}
assert len(rows) == len(mapping) == 70
assert set(mapping) == expected, (set(mapping) ^ expected)
assert all(dest and set(dest) <= tasks for dest in mapping.values())
legacy = {row['id']: row['task_ids'] for row in matrix['scenarios']
          if re.fullmatch(r'TN-\d{2}|J\d{2}', row['id'])}
assert set(legacy) == ({f'TN-{i:02}' for i in range(1, 46)} |
                       {f'J{i:02}' for i in range(1, 35)})
assert all(dest and set(dest) <= tasks for dest in legacy.values())
report = {
    'captured_at': datetime.now(timezone.utc).isoformat(),
    'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip(),
    'status': 'PASS_STATIC_CROSSWALK_AUDIT_ONLY',
    'scope': 'TR4-00-02 requirement succession; not product or gate acceptance',
    'source_sha256': {p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in paths},
    'original_task_destinations': mapping,
    'legacy_scenario_destinations': legacy,
    'task_acceptance_counts': {state: sum(row['acceptance'] == state for row in inventory['tasks'].values())
                               for state in sorted({row['acceptance'] for row in inventory['tasks'].values()})},
    'remaining_ns00_proof': {
        'TR4-00-01': 'Dirty laboratory baseline regression now passes, including current artifact inventory and NUL-separated rename parsing; reconcile this evidence with the full scenario requirements before promotion.',
        'TR4-00-03': 'Direct and legacy endpoint shape tests exist; reconcile client envelope rejection with no-effect evidence.',
        'TR4-00-04': 'Historical r3 codec tests exist; reconcile shared R4 artifact and cross-revision rejection evidence.',
        'TR4-00-05': 'Fixture lost-reply behavior exists; secret isolation and evidence-layer assertions need combined review.'
    },
    'acceptance_inventory_modified': False,
    'gates_closed': []
}
out = root / 'plans/r4_execution/evidence/ns00-crosswalk-audit.json'
out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'status': report['status'], 'tasks': len(mapping), 'scenarios': len(legacy),
                  'acceptance': report['task_acceptance_counts']}))
