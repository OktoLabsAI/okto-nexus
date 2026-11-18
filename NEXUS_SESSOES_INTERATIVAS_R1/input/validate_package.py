#!/usr/bin/env python3
"""Offline documentation-package checks; never runs Nexus, a harness or a provider."""
from __future__ import annotations
import hashlib
import json
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
PLAN = 'PLANO_CODEX_NEXUS_SESSOES_INTERATIVAS_UI_CLI_R1.md'
LEDGER = 'NEXUS_SESSOES_INTERATIVAS_LEDGER_R1.json'
EXPECTED = {'tasks': 41, 'tests': 148, 'requirements': 24, 'phases': 8}


def check() -> dict:
    ledger = json.loads((BASE / LEDGER).read_text(encoding='utf-8'))
    plan = (BASE / PLAN).read_text(encoding='utf-8')
    failures: list[str] = []
    def require(ok: bool, message: str) -> None:
        if not ok:
            failures.append(message)
    require(ledger['plan'] == 'SESSION-INTERACTION-R1', 'Wrong plan version')
    sets = {}
    for kind, expected in EXPECTED.items():
        rows = ledger[kind]
        ids = [x['id'] for x in rows]
        require(len(rows) == expected, f'{kind}: count mismatch')
        require(len(set(ids)) == len(ids), f'{kind}: repeated IDs')
        sets[kind] = set(ids)
    require(ledger['counts'] == EXPECTED, 'Declared counts mismatch')
    referenced_tests, referenced_requirements = set(), set()
    for task in ledger['tasks']:
        require(task['status'] == 'TODO' and not task['evidence'], f"{task['id']}: template not initial")
        require(set(task['depends_on']) <= sets['tasks'], f"{task['id']}: missing dependency")
        require(set(task['test_ids']) <= sets['tests'], f"{task['id']}: missing test")
        require(set(task['requirements']) <= sets['requirements'], f"{task['id']}: missing requirement")
        require(task['phase'] in sets['phases'], f"{task['id']}: missing phase")
        require(bool(task['steps']) and bool(task['acceptance']), f"{task['id']}: incomplete instructions")
        require(re.search(r'^### '+re.escape(task['id'])+r'\s+—', plan, re.M) is not None, f"{task['id']}: absent from Markdown")
        referenced_tests.update(task['test_ids'])
        referenced_requirements.update(task['requirements'])
    require(referenced_tests == sets['tests'], 'Some tests have no accountable task')
    require(referenced_requirements == sets['requirements'], 'Some requirements have no accountable task')
    for test in ledger['tests']:
        require(test['status'] == 'NOT_RUN' and not test['evidence'], f"{test['id']}: test falsely executed")
        require(set(test['requirements']) <= sets['requirements'], f"{test['id']}: missing requirement")
        require(all(test.get(k) for k in ('given','when','then','level')), f"{test['id']}: incomplete scenario")
        require(re.search(r'^### '+re.escape(test['id'])+r'\s+—', plan, re.M) is not None, f"{test['id']}: absent from Markdown")
    graph = {x['id']: x['depends_on'] for x in ledger['tasks']}
    visiting, visited = set(), set()
    def visit(node: str) -> None:
        if node in visiting:
            raise ValueError(f'Dependency cycle at {node}')
        if node in visited:
            return
        visiting.add(node)
        for dep in graph[node]:
            visit(dep)
        visiting.remove(node)
        visited.add(node)
    for node in graph:
        visit(node)
    for phase in ledger['phases']:
        expected_members = {x['id'] for x in ledger['tasks'] if x['phase'] == phase['id']}
        require(set(phase['tasks']) == expected_members, f"{phase['id']}: inconsistent task members")
    task_headings = re.findall(r'^### (SI-\d{3})\s+—', plan, re.M)
    test_headings = re.findall(r'^### (SI-T-[A-Z]\d{2})\s+—', plan, re.M)
    require(set(task_headings) == sets['tasks'] and len(task_headings)==EXPECTED['tasks'], 'Markdown task headings mismatch')
    require(set(test_headings) == sets['tests'] and len(test_headings)==EXPECTED['tests'], 'Markdown test headings mismatch')
    for doc in BASE.glob('*.md'):
        text=doc.read_text(encoding='utf-8')
        fences=re.findall(r'^```.*$',text,re.M)
        require(len(fences)%2==0, f'{doc.name}: unbalanced fenced blocks')
        for block in re.findall(r'^```json\s*\n(.*?)^```\s*$',text,re.M|re.S):
            json.loads(block)
    for f in BASE.glob('*.json'):
        json.loads(f.read_text(encoding='utf-8'))
    matrix=json.loads((BASE/'MATRIZ_CAPACIDADES_SESSAO_R1.json').read_text(encoding='utf-8'))
    require(matrix['plan']==ledger['plan'] and matrix['status']=='TEMPLATE_NOT_QUALIFIED', 'Capability template version/state mismatch')
    require(len(matrix['adapters'])==3 and not matrix['campaigns'], 'Unexpected capability campaigns')
    for adapter in matrix['adapters']:
        require(not adapter['qualified_combinations'], 'Unproven native qualification')
        require(all(v['status']=='designed' and not v['evidence'] for v in adapter['features_to_qualify'].values()), 'Unproven feature evidence')
    manifest_path=BASE/'SHA256SUMS.json'
    if manifest_path.exists():
        manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
        hashes=manifest['files']
        actual_files={p.name for p in BASE.iterdir() if p.is_file() and p.name!='SHA256SUMS.json'}
        require(set(hashes)==actual_files, 'Manifest file membership mismatch')
        for name,digest in hashes.items():
            require(Path(name).name==name, 'Unsafe manifest path')
            path=BASE/name
            require(path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest()==digest, f'{name}: SHA256 mismatch')
    else:
        require('--structure-only' in sys.argv, 'Missing checksum manifest')
    if failures:
        raise ValueError('\n'.join(failures))
    return {'status':'PASS','scope':'DOCUMENT_PACKAGE_ONLY','counts':EXPECTED,
            'checks':['unique_ids','all_refs_resolve','dependency_dag','test_task_coverage',
                      'requirements_task_coverage','markdown_ledger_consistency','json_validity',
                      'fence_balance','initial_statuses','capability_template_unqualified',
                      'sha256_manifest' if manifest_path.exists() else 'structure_only'],
            'application_tests_executed':False,'native_harness_campaigns_executed':False}


if __name__ == '__main__':
    try:
        print(json.dumps(check(),ensure_ascii=False,indent=2))
    except (OSError,ValueError,KeyError,TypeError,RecursionError) as exc:
        print(json.dumps({'status':'FAIL','scope':'DOCUMENT_PACKAGE_ONLY','error':str(exc)},ensure_ascii=False),file=sys.stderr)
        raise SystemExit(1)
