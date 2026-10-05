#!/usr/bin/env python3
"""Validate this planning bundle, NEVER a product or a provider.

Usage: python validar_pacote.py [--root PATH] [--output PATH]
Requires jsonschema for the synthetic shape fixtures. No network,
installation, repository writes, process control, or credential access.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


def read_json(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))


def ensure_acyclic(nodes: dict[str, list[str]]) -> None:
    state: dict[str, int] = {}
    def visit(node: str) -> None:
        if node not in nodes:
            raise AssertionError(f'Dependência ausente: {node}')
        if state.get(node) == 1:
            raise AssertionError(f'Ciclo de dependência em {node}')
        if state.get(node) == 2:
            return
        state[node] = 1
        for dependency in nodes[node]:
            visit(dependency)
        state[node] = 2
    for node in nodes:
        visit(node)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    output = args.output or root / 'evidencias' / 'VALIDACAO_DO_PACOTE.json'
    checks = []
    def run(name, fn):
        try:
            result = fn()
            checks.append({'check': name, 'status': 'PASS', 'detail': result})
        except Exception as exc:
            checks.append({'check': name, 'status': 'FAIL', 'detail': f'{type(exc).__name__}: {exc}'})
    b=read_json(root/'BACKLOG_R4.json');m=read_json(root/'MATRIZ_TESTES_R4.json');c=read_json(root/'RASTREABILIDADE_R3.json')
    phases=b['phases'];tasks=b['tasks'];tests=m['scenarios']
    pids={i['id'] for i in phases};tids={i['id'] for i in tasks};xids={i['id'] for i in tests}
    def basics():
        assert len(pids)==len(phases)==17
        assert len(tids)==len(tasks)==85
        assert len(xids)==len(tests)==164
        assert all(x['status']=='PENDING' for x in phases+tasks)
        assert all(x['status']=='NOT_RUN' for x in tests)
        assert m['all_product_tests_not_run'] is True
        return {'phases':17,'tasks':85,'product_scenarios_not_run':164}
    run('contagens_e_estados_iniciais',basics)
    def dag():
        ensure_acyclic({x['id']:x['depends_on'] for x in phases})
        ensure_acyclic({x['id']:x['dependencies'] for x in tasks})
        return 'DAG de fases e tarefas sem ciclos ou dependência inexistente.'
    run('dependencias',dag)
    def refs():
        for task in tasks:
            assert task['phase_id'] in pids
            for test_id in task['test_ids']:assert test_id in xids, (task['id'],test_id)
        for test in tests:
            for task_id in test['task_ids']:assert task_id in tids,(test['id'],task_id)
        for row in c['original_tasks']:
            assert row['target_task_ids']
            assert set(row['target_task_ids'])<=tids
        return 'Todas as referências tarefa/teste/crosswalk têm destino.'
    run('referencias_internas',refs)
    def original():
        source=(root/'referencias/01_PLANO_NEXUS_SERVER_R3_ORIGINAL.md').read_text(encoding='utf-8')
        orig_tasks=set(re.findall(r'^\| (N\d\d\.\d+) \|',source,re.M))
        orig_tn=set(re.findall(r'^\| (TN-\d\d) \|',source,re.M))
        orig_j=set(re.findall(r'^\| (J\d\d) \|',source,re.M))
        assert len(orig_tasks)==70 and len(orig_tn)==45 and len(orig_j)==34
        assert orig_tasks=={x['id'] for x in c['original_tasks']}
        assert orig_tn|orig_j<=xids
        by={x['id']:x for x in tests}
        for id_ in orig_tn|orig_j:
            line=next(x for x in source.splitlines() if x.startswith('| '+id_+' |'))
            cells=[v.strip() for v in line.strip('|').split('|')]
            assert by[id_]['title']==cells[1],id_
            assert by[id_]['expected']==cells[-1],id_
        return {'original_tasks_mapped':70,'TN_preserved':45,'J_preserved':34}
    run('cobertura_original_R3',original)
    def source_hashes():
        records=read_json(root/'evidencias/REFERENCIAS_HASHES.json')
        for row in records:
            data=(root/row['packaged_file']).read_bytes()
            assert hashlib.sha256(data).hexdigest()==row['sha256'],row['packaged_file']
            assert len(data)==row['bytes']
        return 'Referências anexadas preservadas byte a byte no pacote.'
    run('integridade_referencias',source_hashes)
    def schemas():
        from jsonschema import Draft202012Validator, FormatChecker
        schema=read_json(root/'contratos/http-target.schema.json')
        Draft202012Validator.check_schema(schema)
        routes=read_json(root/'contratos/http-routes.json')['routes']
        assert len(routes)==24
        route_keys={(r['method'],r['path']) for r in routes};assert len(route_keys)==len(routes)
        for route in routes:
            for key in ('request_definition','response_definition'):
                definition=route[key]
                if definition:assert definition in schema['$defs'],definition
        fixture=read_json(root/'contratos/fixtures-planejamento.json')
        results=[]
        for case in fixture['cases']:
            selected={'$schema':schema['$schema'],'$defs':schema['$defs'],'$ref':'#/$defs/'+case['definition']}
            errors=list(Draft202012Validator(selected,format_checker=FormatChecker()).iter_errors(case['data']))
            actual=not errors
            assert actual==case['expect_valid'],(case['id'],[e.message for e in errors[:2]])
            results.append({'id':case['id'],'expected_valid':case['expect_valid'],'observed_valid':actual})
        return {'definitions':len(schema['$defs']),'routes':len(routes),'synthetic_shape_cases':results,'not_product_tests':True}
    run('schemas_e_exemplos_de_forma',schemas)
    def delta():
        delta=read_json(root/'contratos/nxl-r4-delta.json')
        baseline=read_json(root/'evidencias/BASELINE.json')
        assert delta['owner']=='nexus-connector-core'
        assert delta['base_revision']==baseline['core']['wire_revision']
        assert delta['target_revision']==baseline['target']['wire_revision']
        assert delta['base_revision']!=delta['target_revision']
        assert delta['preserve_r3_bytes_and_history'] and delta['new_effects_require_exact_revision']
        assert set(delta['new_frames'])=={'binding.attached','reconcile.accepted','lease.applied'}
        return 'R4 é alvo separado, sem declarar o Core atual como produtor da revisão nova.'
    run('delta_contratual_explicito',delta)
    def docs():
        names=['00_ENTREGAR_AO_AGENTE.md','01_ARQUITETURA_E_PLANO_MESTRE.md','02_CONTRATOS_HTTP_NXL_E_ESTADOS.md','03_DADOS_MIGRACAO_E_RECUPERACAO.md','04_BACKLOG_EXECUCAO.md','05_TESTES_E_ACEITE.md','06_HANDOFF_CORE_CONNECTOR.md','07_RASTREABILIDADE_R3.md','08_FONTES_BASELINE_E_DECISOES.md']
        for name in names:assert (root/name).is_file(),name
        text=(root/'04_BACKLOG_EXECUCAO.md').read_text(encoding='utf-8')
        for id_ in tids:assert id_ in text,id_
        assert (root/'PLANO_COMPLETO_NEXUS_SERVER_R4.md').is_file()
        return 'Documentos, tarefas e versão integral encontrados.'
    run('entregaveis',docs)
    success=all(c['status']=='PASS' for c in checks)
    report={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'status':'PASS' if success else 'FAIL','scope':'document_consistency_and_synthetic_json_shapes_only','product_tests_executed':False,'all_164_product_scenarios':'NOT_RUN','checks':checks}
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    for check in checks:print(f"{check['status']}: {check['check']}")
    print(f'Relatório: {output}')
    return 0 if success else 1

if __name__=='__main__':
    sys.exit(main())
