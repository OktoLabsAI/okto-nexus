"""Read-only DX traceability assembly; never imports or executes product/tests."""
import ast
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

temp = Path(__file__).parent
public = temp/'public'
public.mkdir(exist_ok=True)
repos = dict(Nexus=Path('D:/Projetos/Techridy/okto_labs_okto_nexus'),
             Connector=Path('D:/Projetos/Techridy/okto-nexus-connector'),
             Core=Path('D:/Projetos/Techridy/okto-nexus-connector-core'))
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
write = lambda p,d: p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
plan_path = repos['Nexus']/'PLANO_CODEX_NEXUS_INTEGRACAO_ATENCAO_ONBOARDING.md'
ledger_path = repos['Nexus']/'plans/agent_ops/ledger.json'
plan = plan_path.read_text(encoding='utf-8').splitlines()
ledger = json.loads(ledger_path.read_text(encoding='utf-8'))
specs = json.loads((temp/'decisions.json').read_text(encoding='utf-8'))
xml = json.loads((temp/'xml-index.json').read_text(encoding='utf-8'))
used_inputs = {'Nexus:'+str(p.relative_to(repos['Nexus'])).replace('\\','/'):sha(p) for p in (plan_path,ledger_path)}


def source(reference, *, test=False):
    label, rest = reference.split(':',1)
    relative, _, symbol = rest.partition('#')
    path = repos[label]/relative
    text = path.read_text(encoding='utf-8-sig')
    line, assertions, exception_oracles = 1, [], []
    if symbol and path.suffix == '.py':
        nodes = [n for n in ast.walk(ast.parse(text)) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)) and n.name == symbol]
        assert nodes, reference
        node = nodes[0]
        line = node.lineno
        if test:
            assertions = [dict(line=n.lineno,expression=ast.unparse(n.test)) for n in ast.walk(node) if isinstance(n,ast.Assert)]
            exception_oracles = [dict(line=n.lineno,expression=ast.unparse(item.context_expr))
                for n in ast.walk(node) if isinstance(n,(ast.With,ast.AsyncWith))
                for item in n.items if isinstance(item.context_expr,ast.Call)
                and ast.unparse(item.context_expr.func).endswith('.raises')]
            assert assertions or exception_oracles, reference
    elif symbol:
        line = next(i+1 for i,s in enumerate(text.splitlines()) if re.search(r'\b'+re.escape(symbol)+r'\b',s) and ('function' in s or 'const ' in s))
    result = dict(repository=label,path=relative,line=line,symbol=symbol or None,sha256=sha(path))
    used_inputs[label+':'+relative] = result['sha256']
    if test:
        result['assertions'] = assertions
        result['exception_oracles'] = exception_oracles
    return result


def evidence(test_ref, ledger_tests):
    name = test_ref['symbol']
    module = Path(test_ref['path']).stem
    hits = [h for h in xml.get(name,[]) if module in (h.get('classname') or '')]
    groups = defaultdict(list)
    for item in hits:
        groups[item['path']].append(item)
    good = [(path,items) for path,items in groups.items() if all(x['result']=='PASS' for x in items)]
    assert good, name
    good.sort(key=lambda pair:(('installed' in pair[0]),pair[0] in ledger_tests,
        not any(x in pair[0] for x in ('initial','diagnostic','source-second')),'final' in pair[0],pair[0]),reverse=True)
    path, items = good[0]
    full = repos['Nexus']/path
    used_inputs['Evidence:'+path] = sha(full)
    return dict(path=path,sha256=sha(full),passed_cases=[x['name'] for x in items],
        historical_nonpass_paths=sorted({h['path'] for h in hits if h['result']!='PASS'}),
        meaning='Retained testcase PASS in the cited campaign; this audit did not execute it again.')


matrix = []
for spec in specs:
    ident = spec['id']
    start = next(i for i,s in enumerate(plan) if s.startswith('**'+ident+' '))
    end = next((i for i in range(start+1,len(plan)) if re.match(r'^\*\*DX-\d{2} |^## ',plan[i])),len(plan))
    task = ledger['tasks'][ident]
    row = dict(spec)
    row.update(literal_requirement='\n'.join(plan[start:end]).strip(),plan_line=start+1,
        current_ledger_status=task['status'],existing_nonverified_subscopes={k:v for k,v in task.get('subscopes',{}).items() if v!='VERIFIED'},
        concrete_product_gap='Nenhuma lacuna concreta adicional demonstrada pela revisão deste requisito; distinguir as qualificações listadas de produto ausente.',
        sources=[source(x) for x in spec['sources']])
    row['tests'] = []
    for reference in spec['tests']:
        check = source(reference,test=True)
        check['passed_evidence'] = evidence(check,task['tests'])
        row['tests'].append(check)
    row['reports'] = []
    for path in spec.get('reports',[]):
        full = repos['Nexus']/path
        assert full.exists(), path
        row['reports'].append(dict(path=path,sha256=sha(full)))
        used_inputs['Evidence:'+path] = sha(full)
    matrix.append(row)
assert [r['id'] for r in matrix] == [f'DX-{i:02}' for i in range(1,22)]
svc07 = ('Dependência informada pelo root, não reavaliada nesta auditoria DX: no serviço atual, '
    'CLI/API/coordenador não expõem decisão explícita de força após timeout de drain exigida no plano, linha 325. '
    'Core.shutdown já possui escalada automática de contenção, que não substitui essa decisão. '
    'O caminho de parada controlada exige correção coordenada sem enfraquecer ownership/recuperação.')
scenario_ids = {
    1:[4,5],2:[5,19],3:[13],4:[3],5:[3],6:[3],7:[3],8:[3],9:[4],10:[4,7],11:[4],12:[7],
    13:[7,8],14:[7,8],15:[10],16:[10],17:[10],18:[10],19:[10],20:[10],21:[11],22:[11],23:[11],
    24:[10,11],25:[10,11],26:[6,13],27:[4,14,16],28:[7,11,14],29:[16],30:[16],31:[15],32:[14,19],
    33:[17],34:[7,17,18],35:[7,12],36:[17,18],37:[16,19],38:[18,19],39:[15,18,20],40:[15,18,20],
    41:[17,21],42:[19],43:[18],44:[18],45:[20],46:[10,20],47:[17,20],48:[18],49:[12,21],50:[20],51:[21]}
pending_scenarios = []
for ident, item in ledger['scenarios'].items():
    if not re.fullmatch(r'DX-T\d{2}',ident) or item['status']=='VERIFIED':
        continue
    related = [f'DX-{i:02}' for i in scenario_ids[int(ident[-2:])]]
    pending_scenarios.append(dict(id=ident,ledger_snapshot=item,related_dx_ids=related,
        related_matrix_rows_with_retained_pass=related,
        status_change_recommended=False,
        limit='Mapeamento temático para provas parciais da matriz; não demonstra que o cenário completo foi executado. Status preservado.'))
write(public/'pending-scenarios.json',dict(scope='Snapshot finito dos cenários DX ainda não VERIFIED; sem nova campanha ou promoção',
    ledger_sha256=sha(ledger_path),explicit_not_run=['DX-T27','DX-T34','DX-T39'],scenarios=pending_scenarios,
    external_dependency=dict(id='SVC-07',source='Root review message; not independently reviewed in this DX audit',
        statement=svc07,applies_to='Caminho de parada controlada e seus consumidores; impede alegar que todo o produto de serviço está completo.')))
write(public/'matrix.json',dict(scope='SAFE-TRACE/AC01 read-only audit of 21 original DX IDs',
    generated_at=datetime.now(timezone.utc).isoformat(), plan_sha256=sha(plan_path),
    new_test_runs=0, product_changes=0, ledger_changes=0, recommendations_applied=False,
    recommendation_scope='Per literal DX requirement. Does not close AC01/full R3, real-client credential chain or productive M1/M2.',
    pending_scenarios='pending-scenarios.json',external_dependency=svc07,
    tasks=matrix))
md = ['# Matriz DX — SAFE-TRACE / AC01','',
      'Auditoria somente leitura dos 21 IDs originais. Nenhum teste/campanha foi executado, nenhum produto ou ledger foi editado. Recomendações abaixo não foram aplicadas.', '',
      'As evidências selecionadas são PASS efetivamente presentes em XMLs retidos, ou relatórios de campanha identificados por hash. Cada teste em matrix.json inclui as assertions e/ou oráculos de exceção esperada atuais e suas linhas. Os PASS comprovam a campanha citada; esta leitura não requalifica automaticamente todos os bytes do pacote atual. Relatórios iniciais com falha continuam referenciados. Não somar campanhas sobrepostas como testes únicos.', '',
      'Recomendação por requisito literal: contratos puros não herdam automaticamente a pendência produtiva de M1/M2. Mesmo os IDs recomendados VERIFIED abaixo não encerram AC01/full R3, cofre→cliente real ou M1/M2.', '',
      'DX-T27, DX-T34 e DX-T39 permanecem NOT_RUN. O snapshot dos demais cenários DX pendentes, seus limites e relações temáticas está em pending-scenarios.json; nenhuma prova parcial da matriz encerra esses cenários automaticamente.', '',svc07,'',
      '| ID | Ledger atual | Recomendação | Pendência do próprio ID |','|---|---|---|---|']
for row in matrix:
    md.append('| '+ ' | '.join((row['id'],row['current_ledger_status'],row['recommendation'],'Qualificação real listada abaixo' if row['pending'] else 'Nenhuma lacuna literal demonstrada'))+' |')
for row in matrix:
    md += ['', '## '+row['id'], '', '**Requisito literal** — plano fixo, linha '+str(row['plan_line'])+'.', '',row['literal_requirement'],'',
           '**Implementação/reuso:** '+row['implementation'],'','Fontes atuais:','']
    md += ['- '+x['repository']+': `'+x['path']+':'+str(x['line'])+'`'+(' — `'+x['symbol']+'`.' if x['symbol'] else '.') for x in row['sources']]
    md += ['', 'Testes/assertions e PASS retidos (expressões exatas em matrix.json):','']
    for check in row['tests']:
        ev=check['passed_evidence']
        md.append('- `'+check['path']+':'+str(check['line'])+'` — `'+check['symbol']+'`; '+str(len(check['assertions'])+len(check['exception_oracles']))+' oráculos (assert/raises); '+str(len(ev['passed_cases']))+' caso(s) PASS em `'+ev['path']+'`.')
    if row['reports']:
        md += ['', 'Relatórios complementares: '+', '.join('`'+x['path']+'`' for x in row['reports'])+'.']
    md += ['', '**Lacuna de produto:** '+row['concrete_product_gap'], '', '**Qualificação pendente:**']
    md += ['']+(['- '+x for x in row['pending']] if row['pending'] else ['Nenhuma campanha adicional necessária para o requisito literal indicado; os aceites gerais permanecem separados.'])
    md += ['', '**Recomendação:** '+row['recommendation']+'. '+row['status_reason'],'','**Reconciliação de texto/status herdado:** '+row['stale']]
(public/'matrix.md').write_text('\n'.join(md)+'\n',encoding='utf-8')
heads = {name:subprocess.check_output(['rtk','git','-C',str(path),'rev-parse','HEAD'],text=True).strip() for name,path in repos.items()}
write(public/'input-manifest.json',dict(repository_heads=heads,files=used_inputs))
for name in ('decisions.json','index.py','build_matrix.py'):
    shutil.copy2(temp/name,public/name)
counts = dict(Counter(row['recommendation'] for row in matrix))
write(public/'summary.json',dict(tasks=21,recommended_statuses=counts,additional_dx_product_gaps_demonstrated=0,
    known_external_dependency=svc07,pending_scenarios=len(pending_scenarios),
    new_test_runs=0, ledger_edited=False, key_pending=['DX-02 broad real-vault/client chain remains NOT_RUN',
    'DX-04 actual protected credential delivery chain', 'DX-08 external-client canonical cooperation',
    'DX-15/16/17/18/20 real qualified local and Connector default path'],
    stale_metadata=['generic terminal/remote grant renewal statuses after the delivered renewal milestone',
                    'old participant init/launcher missing-product language', 'old remote identity/workspace bootstrap missing-product language',
                    'old dashboard secret/origin snippet language'],
    global_limits=['No automatic promotion of AC01/full R3 or M1/M2','Historical XML PASS is not a new current-wheel run']))
allowlist = ['README.md','matrix.json','matrix.md','pending-scenarios.json','input-manifest.json','summary.json','decisions.json','index.py','build_matrix.py']
write(public/'manifest.json',{name:dict(sha256=sha(public/name),bytes=(public/name).stat().st_size) for name in allowlist})
print(json.dumps(dict(public=str(public),tasks=21,recommendations=counts,artifacts=len(allowlist)+1,
    manifest_sha256=sha(public/'manifest.json')),indent=2))
