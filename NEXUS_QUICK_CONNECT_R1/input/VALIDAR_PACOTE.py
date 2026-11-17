#!/usr/bin/env python3
"""Validate only this specification package; never call Git, Nexus or a provider."""
from pathlib import Path
import hashlib
import json
import re
import sys

PLAN = 'PLANO_CODEX_NEXUS_QUICK_CONNECT_CWD_ID_R1_CONSOLIDADO.md'
LEDGER = 'NEXUS_QUICK_CONNECT_LEDGER_R1.json'
PROMPT = 'PROMPT_CODEX_NEXUS_QUICK_CONNECT_R1.md'
EXPECTED_COUNTS = {'tasks': 33, 'tests': 147, 'requirements': 20, 'increments': 7}
GROUP_COUNTS = {'A': 16, 'B': 10, 'C': 18, 'D': 26, 'E': 18, 'F': 24, 'G': 15, 'H': 10, 'I': 10}


def validate(root: Path) -> dict:
    checks: list[str] = []

    def check(name: str, condition: bool) -> None:
        if not condition:
            raise ValueError('Falha: ' + name)
        checks.append(name)

    data = json.loads((root / LEDGER).read_text(encoding='utf-8'))
    text = (root / PLAN).read_text(encoding='utf-8')
    prompt = (root / PROMPT).read_text(encoding='utf-8')
    readme = (root / 'LEIA-ME.md').read_text(encoding='utf-8')
    tasks, tests, requirements, phases = (data[k] for k in ('tasks', 'tests', 'requirements', 'phases'))
    ts, xs, rs = ({row['id']: row for row in rows} for rows in (tasks, tests, requirements))

    check('edição inicial consolidada R1', data['plan'] == 'QCONNECT-R1'
          and data['edition'] == 'consolidated_initial_delivery' and 'QCONNECT-R1' in text)
    check('nenhum plano externo obrigatório', data['external_plan_dependencies'] == [])
    check('contagens esperadas', data['counts'] == EXPECTED_COUNTS
          and len(tasks) == 33 and len(tests) == 147 and len(requirements) == 20 and len(phases) == 7)
    check('IDs únicos', len(ts) == len(tasks) and len(xs) == len(tests) and len(rs) == len(requirements))
    check('tarefas numeradas em ordem', [t['id'] for t in tasks] == [f'QC-{i:03d}' for i in range(1, 34)])
    check('requisitos numerados em ordem', [r['id'] for r in requirements] == [f'QC-R{i:02d}' for i in range(1, 21)])
    expected_tests = {f'QC-T-{g}{i:02d}' for g, n in GROUP_COUNTS.items() for i in range(1, n+1)}
    check('cenários completos por grupo', set(xs) == expected_tests)
    check('etapas completas', [p['id'] for p in phases] == [f'QC-{i:02d}' for i in range(7)])
    check('etapas correspondem ao backlog', all(p['task_ids'] == [t['id'] for t in tasks if t['phase'] == p['id']] for p in phases)
          and {t['phase'] for t in tasks} == {p['id'] for p in phases})

    check('dependências existentes', all(set(t['depends_on']) <= set(ts) for t in tasks))
    position = {t['id']: i for i, t in enumerate(tasks)}
    check('dependências anteriores ao consumidor', all(position[d] < position[t['id']] for t in tasks for d in t['depends_on']))
    check('requisitos das tarefas válidos', all(t['requirements'] and set(t['requirements']) <= set(rs) for t in tasks))
    check('testes das tarefas válidos', all(t['test_ids'] and set(t['test_ids']) <= set(xs) for t in tasks))
    check('tarefas dos testes válidas', all(x['tasks'] and set(x['tasks']) <= set(ts) for x in tests))
    check('relações tarefa-teste bidirecionais',
          all(t['id'] in xs[x]['tasks'] for t in tasks for x in t['test_ids'])
          and all(x['id'] in ts[t]['test_ids'] for x in tests for t in x['tasks']))
    check('todos os requisitos cobertos', set(rs) <= {r for t in tasks for r in t['requirements']})
    check('tarefas iniciam TODO sem evidência', all(t['status'] == 'TODO' and not t['evidence'] for t in tasks))
    check('cenários iniciam NOT_RUN sem evidência', all(x['status'] == 'NOT_RUN' and not x['evidence'] for x in tests))
    check('requisitos ainda não verificados', all(r['status'] == 'NOT_VERIFIED' for r in requirements))
    check('sem metadados de revisão incremental', all(k not in data for k in
          ('parent_plan', 'derived_from', 'revision_delta', 'revised', 'revision_scope', 'evidence_inheritance'))
          and not any('introduced_in' in r or 'updated_in' in r for r in tasks + tests + requirements))

    md_tasks = dict(re.findall(r'^### (QC-\d{3}) — (.*)$', text, re.M))
    md_tests = dict(re.findall(r'^### (QC-T-[A-Z]\d{2}) — (.*)$', text, re.M))
    md_requirements = dict(re.findall(r'^\| (QC-R\d{2}) \| (.*?) \|$', text, re.M))
    check('tarefas Markdown/JSON iguais', md_tasks == {t['id']: t['title'] for t in tasks})
    check('cenários Markdown/JSON iguais', md_tests == {t['id']: t['title'] for t in tests})
    check('requisitos Markdown/JSON iguais', md_requirements == {r['id']: r['description'] for r in requirements})
    for t in tasks:
        pattern = rf'^### {re.escape(t["id"])} — .*?\n(.*?)(?=^### QC-|^## QC-|^# 13\.|\Z)'
        match = re.search(pattern, text, re.M | re.S)
        if match is None:
            raise ValueError('Bloco ausente: ' + t['id'])
        block = match[1]
        dep = ', '.join(t['depends_on']) or 'nenhuma'
        check('contrato completo: ' + t['id'], f'**Dependências:** {dep}.' in block
              and f'**Requisitos:** {", ".join(t["requirements"])}.' in block
              and all(f'{i}. {s}' in block for i, s in enumerate(t['steps'], 1))
              and f'**Aceite:** {t["acceptance"]}' in block
              and f'**Cenários relacionados:** {", ".join(t["test_ids"])}.' in block)
    check('todos os passos de aceite no Markdown', all(
        f'**Dado:** {x["given"]}. **Quando:** {x["when"]}. **Então:** {x["then"]}.' in text
        for x in tests))
    references = set(re.findall(r'\b(?:QC-T-[A-Z]\d{2}|QC-R\d{2}|QC-\d{3})\b', text))
    check('referências internas sem IDs órfãos', references <= set(ts) | set(xs) | set(rs))
    check('baseline registrado', data['sha_reference'] == '2463c05833f533bc5a5676a5644774cff949ca28'
          and data['sha_reference'] in text and data['sha_reference'] in prompt)
    check('entrada aponta aos arquivos corretos', data['plan_file'] == PLAN and data['prompt_file'] == PROMPT
          and PLAN in prompt and LEDGER in prompt and PLAN in readme and PROMPT in readme)
    check('Markdown com fences balanceados', len(re.findall(r'^```', text, re.M)) % 2 == 0)
    samples = re.findall(r'^```json\s*\n(.*?)^```\s*$', text, re.M | re.S)
    for sample in samples:
        json.loads(sample)
    check('exemplos JSON válidos', bool(samples))
    check('rótulo e contrato público no prompt', 'ID do Harness' in prompt and 'connect_id' in prompt and '--id' in prompt)
    check('descoberta Git e raiz independente no prompt', 'Git' in prompt and 'CWD' in prompt and 'raiz de execução' in prompt)
    check('colisões e confirmação no prompt', '**Colisões:**' in prompt and '**Confirmação:**' in prompt and '--new-connection' in prompt)
    forbidden = re.compile(r'(?i)\bQCONNECT-R2\b|_R2\b|\bR2\b|\bUI-R1\b|\bHOME-R1\b|\bplano pai\b|\badendo\b|\bnovo em R\d\b')
    check('documentos sem dependência de emendas', all(not forbidden.search(s) for s in (text, prompt, readme, json.dumps(data, ensure_ascii=False))))
    check('arquivo de changelog incremental ausente', not any(p.name.startswith('ALTERACOES') for p in root.iterdir()))

    manifest_verified = False
    manifest_path = root / 'SHA256.json'
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        for name, digest in manifest['files'].items():
            rel = Path(name)
            check('caminho seguro: ' + name, not rel.is_absolute() and '..' not in rel.parts
                  and len(rel.parts) == 1 and not (root / rel).is_symlink())
            check('checksum: ' + name, hashlib.sha256((root / rel).read_bytes()).hexdigest() == digest)
        expected = {p.name for p in root.iterdir() if p.is_file() and p.name != 'SHA256.json'}
        check('manifesto cobre todos os arquivos', set(manifest['files']) == expected)
        manifest_verified = True
    return {'status': 'PASS', 'plan': data['plan'],
            'scope': 'specification_structure_and_package_integrity_only',
            'nexus_tests_executed': False, 'repository_modified': False,
            'counts': data['counts'], 'checks': checks, 'checks_count': len(checks),
            'manifest_verified': manifest_verified}


if __name__ == '__main__':
    try:
        result = validate(Path(__file__).resolve().parent)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({'status': 'FAIL', 'message': str(exc)}, ensure_ascii=False, indent=2))
        sys.exit(1)
    print(json.dumps(result, ensure_ascii=False, indent=2))
