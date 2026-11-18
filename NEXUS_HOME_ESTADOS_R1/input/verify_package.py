"""Validate this planning package, not the Nexus application."""
from pathlib import Path
import hashlib
import json
import re
import sys


def main() -> int:
    root=Path(__file__).resolve().parent
    manifest=json.loads((root/'MANIFEST_SHA256.json').read_text(encoding='utf-8'))
    for name, expected in manifest['files'].items():
        path=root/name
        if path.parent != root or not path.is_file():
            raise ValueError(f'Missing/invalid package file: {name}')
        if hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
            raise ValueError(f'Checksum mismatch: {name}')
    ledger=json.loads((root/'NEXUS_HOME_ESTADOS_LEDGER_R1.json').read_text(encoding='utf-8'))
    plan=(root/ledger['plan_file']).read_text(encoding='utf-8')
    tasks={x['id']:x for x in ledger['tasks']}
    tests={x['id']:x for x in ledger['tests']}
    reqs={x['id'] for x in ledger['requirements']}
    if len(tasks)!=len(ledger['tasks']) or len(tests)!=len(ledger['tests']):
        raise ValueError('Duplicate task/test IDs')
    if len(tasks)!=ledger['counts']['tasks'] or len(tests)!=ledger['counts']['tests'] or len(reqs)!=ledger['counts']['requirements']:
        raise ValueError('Count mismatch')
    if set(re.findall(r'^### (HST-\d{3}) —',plan,re.M))!=set(tasks):
        raise ValueError('Plan task headings mismatch')
    if set(re.findall(r'^### (HST-T-[A-Z]\d{2}) —',plan,re.M))!=set(tests):
        raise ValueError('Plan test headings mismatch')
    covered=set()
    for t in tasks.values():
        if t['status'] not in ledger['task_statuses']:
            raise ValueError('Invalid task status')
        if not set(t['dependencies']) <= set(tasks) or not set(t['requirements']) <= reqs or not set(t['tests']) <= set(tests):
            raise ValueError(f'Broken references: {t["id"]}')
        covered.update(t['tests'])
    if covered!=set(tests):
        raise ValueError('Some tests have no owning task')
    if any(t['status'] not in ledger['test_statuses'] for t in tests.values()):
        raise ValueError('Invalid test status')
    stages=ledger['stages']
    if len(stages)!=ledger['counts']['stages'] or sorted(x for s in stages for x in s['task_ids'])!=sorted(tasks):
        raise ValueError('Stage/task membership mismatch')
    for s in stages:
        if any(tasks[t]['stage']!=s['id'] for t in s['task_ids']):
            raise ValueError('Wrong stage membership')
    visited=set()
    def visit(key, stack):
        if key in stack:
            raise ValueError(f'Cycle at {key}')
        if key in visited: return
        for dep in tasks[key]['dependencies']:
            visit(dep,stack|{key})
        visited.add(key)
    for key in tasks: visit(key,set())
    referenced=set(re.findall(r'\[S(\d{2})\]',plan))
    defined=set(re.findall(r'\*\*\[S(\d{2})\]',plan))
    if not referenced<=defined:
        raise ValueError('Missing source definitions')
    if plan.count('```') % 2:
        raise ValueError('Unbalanced Markdown code fence')
    print(json.dumps({'package_validation':'PASS','tasks':len(tasks),'tests':len(tests),'requirements':len(reqs),'stages':len(stages),'nexus_tests_executed':False},ensure_ascii=False,indent=2))
    return 0


if __name__=='__main__':
    try:
        raise SystemExit(main())
    except (OSError,ValueError,KeyError,TypeError) as exc:
        print(f'Package validation failed: {exc}', file=sys.stderr)
        raise SystemExit(1)
