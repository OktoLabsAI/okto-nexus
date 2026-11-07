"""Read retained artifacts only; no tests, imports of product, or checkout writes."""
import ast
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET
from collections import Counter

BASE = Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
OUT = Path(__file__).parent
REPOS = {'nexus': BASE, 'connector': BASE.parent / 'okto-nexus-connector', 'core': BASE.parent / 'okto-nexus-connector-core'}
E = 'plans/agent_ops/evidence/'
DX = E + 'r3-task-reconciliation/dx/matrix.json'
AT = E + 'r3-task-reconciliation/atn-obs/matrix.json'
SV = E + 'r3-task-reconciliation/svc/audit.json'
JO = E + 'r3-joint-contracts/integration.json'
inputs = {}
checks = []

def digest(data):
    return hashlib.sha256(data).hexdigest()

def path_ref(path, repository='nexus', **extra):
    p = REPOS[repository.lower()] / path
    raw = p.read_bytes()
    key = repository.lower() + ':' + path
    inputs[key] = dict(repository=repository.lower(), path=path, sha256=digest(raw), bytes=len(raw))
    return dict(inputs[key], **extra)

def read(path, repository='nexus'):
    path_ref(path, repository)
    return json.loads((REPOS[repository.lower()] / path).read_text(encoding='utf-8'))

dx = {x['id']: x for x in read(DX)['tasks']}
at = read(AT)
sv = read(SV)
jo = read(JO)
ledger = read('plans/agent_ops/ledger.json')
plan_path = 'PLANO_CODEX_NEXUS_INTEGRACAO_ATENCAO_ONBOARDING.md'
plan_ref = path_ref(plan_path)
plan_rows = {}
for line, text in enumerate((BASE / plan_path).read_text(encoding='utf-8').splitlines(), 1):
    m = re.match(r'^\|\s*(INV-\d{2})\s*\|\s*(.*?)\s*\|$', text)
    if m:
        plan_rows[m[1]] = (line, m[2])
assert len(plan_rows) == 28, len(plan_rows)

def source(s):
    repository = s.get('repository', 'nexus').lower()
    if repository not in REPOS:
        raise ValueError(repository)
    out = path_ref(s['path'], repository, symbol=s.get('symbol'), retained_line=s.get('line'))
    if s.get('sha256'):
        out['retained_catalog_sha256'] = s['sha256']
        out['same_bytes_as_catalog'] = out['sha256'] == s['sha256']
    return out

def passed(path, names, repository='nexus'):
    ref = path_ref(path, repository)
    tree = ET.parse(REPOS[repository] / path)
    cases = tree.findall('.//testcase')
    matched = []
    for name in names:
        selected = [c for c in cases if c.get('name') == name or c.get('name', '').startswith(name + '[')]
        if not selected:
            raise ValueError(f'missing retained testcase {path}: {name}')
        for c in selected:
            if any(c.find(k) is not None for k in ('failure', 'error', 'skipped')):
                raise ValueError(f'nonpass cited as pass {path}: {c.get("name")}')
            matched.append(c.get('classname', '') + '::' + c.get('name', ''))
    checks.append(dict(report=ref, matched_cases=sorted(set(matched)), action='read retained XML only'))
    return dict(ref, passed_cases=sorted(set(matched)))

def dx_refs(ids, count=2):
    refs, sources = [], []
    for ident in ids:
        item = dx[ident]
        refs.append(path_ref(DX, locator=f'tasks[id={ident}]', assertion=item['implementation']))
        sources.extend(source(s) for s in item['sources'])
        for t in item['tests'][:count]:
            p = t['passed_evidence']['path']
            report = passed(p, t['passed_evidence']['passed_cases'])
            refs.append(dict(report, test_source=source(t), assertions=t.get('assertions', []),
                             exception_oracles=t.get('exception_oracles', [])))
        refs.extend(path_ref(r['path']) for r in item['reports'])
    return refs, sources

def at_refs(bundles, count=2):
    refs, sources = [], []
    for name in bundles:
        b = at['proof_bundles'][name]
        refs.append(path_ref(AT, locator=f'proof_bundles.{name}', assertion=b['behavior']))
        sources.extend(path_ref(p) for p in b['implementation'])
        for key in b['tests'][:count]:
            t = at['test_proofs'][key]
            r = t['selected_passing_report']
            refs.append(dict(passed(r['path'], [t['name']]), test_source=path_ref(t['source'], retained_line=t['line']),
                             assertions=t.get('assertions', []), exception_oracles=t.get('raises', [])))
        refs.extend(path_ref(p) for p in b['additional_evidence'])
        if b['frontend_tests']:
            refs.append(path_ref(AT, locator=f'proof_bundles.{name}.frontend_tests', assertions=b['frontend_tests']))
    return refs, sources

def svc_refs(keys, implementation):
    refs, sources = [], [source(sv['implementation'][k]) for k in implementation]
    for k in keys:
        x = sv['evidence'][k]
        refs.append(path_ref(SV, locator='evidence.' + k, assertion=x['assertion_read'], limit=x['limits']))
        groups = {}
        for p in x['retained_passes']:
            groups.setdefault(p['report'], []).append(p['name'])
        for p, names in groups.items():
            refs.append(passed(p, names))
    return refs, sources

def joint_refs(needles):
    refs, sources = [], []
    for needle in needles:
        selected = [(key, val) for key, val in jo['case_reports'].items() if needle in key]
        assert selected, needle
        for key, relative in selected:
            refs.append(passed(E + 'r3-joint-contracts/' + relative, [key.split('::', 1)[1]]))
            module = key.split('::')[0].replace('.', '/') + '.py'
            sources.append(path_ref(module))
    return refs, sources

rows = []
def row(n, reason, limit, groups=(), docs=(), source_paths=(), conditional=False, kind='architectural_contract'):
    ident = f'INV-{n:02}'
    line, literal = plan_rows[ident]
    assert literal == ledger['invariants'][ident]['requirement'], ident
    refs, sources = [], []
    for a, b in groups:
        refs.extend(a)
        sources.extend(b)
    for p in docs:
        refs.append(path_ref(p))
    for p in source_paths:
        sources.append(path_ref(p))
    rows.append(dict(id=ident, literal_requirement=literal, plan_line=line,
                     current_status=ledger['invariants'][ident]['status'],
                     proposed_status='CONDITIONAL_PENDING_QUALIFIED' if conditional else 'VERIFIED',
                     kind=kind, reason=reason, evidence=refs, implementation=sources, limit=limit,
                     acceptance_change='none; does not close M1/M2 or global R3'))

scope = 'Windows/local e contratos canônicos com pares nativos sintéticos. Não qualifica provedor pessoal, serviço nativo registrado nem outras plataformas.'
pending = 'Core e Connector drain instalados qualificados; delta Nexus SVC-07 congelado, mas os 36 novos casos/247 de regressão informados pelo owner ainda não são evidência aceita nesta auditoria. Condicionar promoção ao pacote/relatório final Nexus, sem executar nada aqui.'

row(1, 'Identidade selecionada e autenticada permanece agent_id; sessões/instâncias e fontes têm seus próprios IDs auxiliares.', scope,
    [joint_refs(['test_rg01_']), at_refs(['registration']), dx_refs(['DX-19'], 1)])
row(2, 'Participante conecta diretamente ao MCP HTTP do Server; exportação/guia e observador não criam servidor MCP intermediário. O Connector mantém o canal R4 de execução.',
    'Formato HTTP e separação de transporte verificados; não se converte configuração em prova de execução nativa. Nenhum MCP stdio novo.',
    [dx_refs(['DX-01','DX-09'], 1), at_refs(['observer_readonly'], 1)],
    [E+'pr05-coordination-cli.md', E+'pr04-participant-guide/milestone.md'],
    ['src/okto_nexus/adapters/outbound/participant_coordination_mcp.py'])
row(3, 'Boundaries retidos excluem dependências entre aplicações. Core recebe contratos/ports de execução, e o drain novo apenas metadata de runtime/journal.',
    'A auditoria de import com guards é do wheel Core 5721; não é reclassificada como execução do wheel 140701. O delta Core atual é revisado estaticamente abaixo e a qualificação instalada própria é separada.',
    docs=[E+'r3-compatibility-boundaries/core/report.json', E+'r3-compatibility-boundaries/core/application-boundaries.json',
          E+'r3-joint-contracts/core/observation.json', '../okto-nexus-connector-core/docs/evidence/cooperative-drain/summary.json',
          '../okto-nexus-connector-core/docs/evidence/cooperative-drain/milestone.md'])
row(4, 'Claim, entrega e decisões permanecem serviços canônicos Server; Connector realiza a execução do binding autorizado via R4, sem inbox/handoff próprios.', scope,
    [joint_refs(['test_remote_domain_delivery_keeps_exclusive_claim_from_mcp'])],
    [E+'r3-joint-contracts/mixed/mapping.json'],
    ['src/okto_nexus/application/handoff.py', '../okto-nexus-connector/src/okto_nexus_connector/daemon/r4_execution.py'])
row(5, 'Projeção distingue estados e proveniência; publicação externa não toca coordenação/presença/capacidade e recibo recebido não vira liveness/idle.', scope,
    [at_refs(['canonical_isolation','correlation'], 1), dx_refs(['DX-07'], 2)])
row(6, 'Idle/done externos não liberam turno/reserva nem alteram prioridade/fairness; timeout de observação não cancela. Novo drain requer prova de quiescência ou força explícita e retém UNKNOWN.',
    pending, [at_refs(['canonical_isolation'], 2), joint_refs(['test_external_idle_preserves_exact_unconsumed_claim_reservation']), dx_refs(['DX-11'], 2)],
    ['../okto-nexus-connector/docs/evidence/cooperative-drain/installed/reports.json', '../okto-nexus-connector-core/docs/evidence/cooperative-drain/summary.json'], conditional=True)
row(7, 'GET/inspeção e preferências são passivos sobre tabelas canônicas; decisões exigem controles existentes, autoridade e CAS.', scope,
    [at_refs(['passive','ui','interaction'], 1)])
row(8, 'OBS publica somente estado auxiliar. Correlação é operador-only, prova nativa/OS não vem do cliente e não transfere autoridade ao sinal externo.', scope,
    [at_refs(['canonical_isolation','correlation'], 2)])
row(9, 'Corridas MCP/runtime resultam em um único claim e efeito; inelegibilidade não muda com idle externo e MCP-only participa sem relatório externo.', scope,
    [joint_refs(['test_rg02_', 'test_canonical_push_reservation_excludes_mcp_pull']), at_refs(['off'], 1)])
row(10, 'Recovery preserva request/operation/decisão originais; ausência/uncertainty não cria substituto e novo trabalho exige intenção explícita.',
    'Deduplicação canônica e recuperação qualificadas; não se promete exactly-once de efeitos externos arbitrários.',
    [dx_refs(['DX-10'], 2), joint_refs(['test_lost_submission_response_recovers_same_work', 'test_missing_previously_confirmed_receipt'])])
row(11, 'Credenciais entram por mecanismos protegidos e referências; checkpoints/exportações omitem valores. Correção dos artefatos públicos foi revisada e itens sintéticos classificados.',
    'Prova do snapshot público e dos caminhos exercitados; não é auditoria de toda história Git nem declaração de ausência universal de vazamentos. Material one-shot não é capturado em screenshot. Cofre→cliente real completo segue NOT_RUN.',
    [dx_refs(['DX-04','DX-19'], 1), at_refs(['untrusted'], 1)],
    [E+'r3-public-artifact-review/verification.json', E+'r3-public-artifact-review/classifications.json', E+'pr04-participant-guide/reports.json'])
row(12, 'Contrato ParticipantClientConfig é distinto de capacidade/qualificação managed; cliente/build não observado fica UNKNOWN e generic/Pi não recebem adapter HTTP inventado.',
    'VERIFIED é a honestidade da qualificação. Parsing e initialize reais não são inferência nativa nem cadeia completa cofre→launcher→cliente; M1/M2 não promovidos.',
    [dx_refs(['DX-01','DX-02'], 3)], [E+'pr04-participant-guide/milestone.md'], kind='qualification_honesty')
row(13, 'A central compõe fatos canônicos e guarda só preferências/anchors; observações/correlações são auxiliares e reads preservam tabelas canônicas.', scope,
    [at_refs(['projection','preferences','correlation'], 1)])
row(14, 'Schema fechado recusa campos de identidade/comando; texto de terminal é dado escapado e somente evento canônico pode concluir trabalho.', scope,
    [at_refs(['untrusted','canonical_isolation'], 2), dx_refs(['DX-11'], 1)])
row(15, 'CLI reutiliza ferramentas canônicas; schemas e descoberta validam parâmetros antes do efeito. Mudanças MCP têm medições de superfície retidas e teste de orçamento.',
    'Revisão da superfície alterada neste plano; não equivale a aprovação irrestrita de futuras ferramentas.',
    [dx_refs(['DX-09'], 1)], [E+'pr05-coordination-cli-surface.json', E+'pr05-coordination-creation-surface-final.json', E+'pr04-cooperation-surface.json', E+'pr05-coordination-cli.md'],
    ['src/okto_nexus/adapters/inbound/mcp/registration.py', 'tests/test_participant_coordination_mcp.py'])
rows[-1]['evidence'].append(passed(E+'pr05-coordination-cli-surface-installed.xml', ['test_s4_cuttable_surface_meets_40pct_reduction_gate']))
rows[-1]['evidence'].append(passed(E+'pr05-coordination-cli-source-participant-coordination-mcp-agent.xml', ['test_invalid_call_is_refused_before_transport','test_real_tcp_discovery_creation_and_recovery_use_canonical_identity']))
row(16, 'Lifecycle compõe o mesmo Server/DaemonApp e os mesmos contratos Core, sem segundo scheduler, fila produtiva ou identidade de agente.', scope,
    [svc_refs(['E01','E02'], ['facade','foreground','supervised','detached','connector_lifecycle'])], [ 'plans/agent_ops/adr.md'])
row(17, 'Instância é derivada de home/DB/usuário e protegida por exclusão OS/generation antes de bootstrap. Alias/perfis não permitem dois owners dos mesmos dados.',
    'Exclusão real de processos Windows observada; não se generaliza a plataformas não qualificadas.',
    [svc_refs(['E03','E04'], ['instance','lock','locking','connector_lifecycle'])])
row(18, 'Topology é resolvida antes de lifecycle local; RemoteTarget apenas verifica Server remoto e não oferece fallback de início local.', scope,
    [svc_refs(['E06','E17'], ['topology','connect','connector_connect'])])
row(19, 'Start instalado usa o gerenciador nativo e não lança daemon avulso. Intent/lock existentes impedem concorrência e submissão repetida enquanto pendente.',
    'Contrato de roteamento/supervisor com adapter injetado + lock/processo real; registro/login do Task Scheduler ainda são campanhas distintas não executadas.',
    [svc_refs(['E07','E08'], ['installation','local','connector_install','connector_lifecycle'])])
row(20, 'Reuso/recovery não emite novos grants nem repete resultado incerto; leases antigas não migram na renovação explícita. Novo stop/restart mantém latch antes dos efeitos.',
    pending, [svc_refs(['E07','E18'], ['shutdown','local','connector_lifecycle']), joint_refs(['test_checkpoint_loss_preserves_uncertainty_without_respawn'])],
    ['../okto-nexus-connector/docs/evidence/cooperative-drain/installed/reports.json'], conditional=True)
row(21, 'Saída do launcher/CLI mantém owner e trabalho; parada explícita fixa desired=draining antes da contenção. Direct IPC também precisa latch de supervisor.',
    pending + ' Não se usa saída do launcher como prova de logout/reboot.',
    [svc_refs(['E01','E02','E11'], ['shutdown','local','connector_lifecycle']), dx_refs(['DX-20'], 3)],
    ['../okto-nexus-connector/docs/evidence/cooperative-drain/installed/reports.json'], conditional=True)
row(22, 'Readiness correlaciona owner/versão mas não afirma login/provedor/participação/trabalho. Doctor mantém checks/proof levels independentes.', scope,
    [svc_refs(['E05'], ['readiness','inspect']), dx_refs(['DX-07'], 3)])
row(23, 'Status/log/doctor padrão são observações sem start/cofre/rede/inferência; connect de ação usa ensure_running somente após revisão/ação documentada.',
    'Modos ativos de doctor são explícitos; ausência de serviço não é ausência de trabalho.',
    [svc_refs(['E06','E16'], ['doctor','logs','service_cli','connector_doctor']), dx_refs(['DX-14'], 3)])
row(24, 'Relatórios distinguem saída de launcher, reinício sintético, login, logout/reboot e operação sem login; a campanha nativa preparada permanece não executada.',
    'VERIFIED verifica honestidade/segregação de evidência, não transforma preparação ou detached em campanha de login/reboot. Outras plataformas não qualificadas.',
    [svc_refs(['E01','E02','E09'], ['context','connector_context'])],
    [E+'r3-qualification-readiness/native-proposal/native-service-campaign-proposal.json', 'plans/agent_ops/campaigns/windows-user-service.md'], kind='qualification_honesty')
row(25, 'Connect/init/work/decisões usam CLI e autoridade canônica vigente; fluxo padrão não exige dashboard e políticas preexistentes seguem obrigatórias.',
    'VERIFIED para completude contratual da UX terminal demonstrada com peer sintético. Uso produtivo real do caminho escolhido continua gate M1/DX-20; não há alegação de campanha real.',
    [dx_refs(['DX-05','DX-19','DX-20'], 2)], [E+'pr03-terminal-work.md', 'docs/terminal-connect.md','docs/terminal-work.md'])
row(26, 'Preset é configuração versionada reutilizável, não identidade global. Finish/reconnect recuperam mesmo agente; merge só avança defaults não personalizados.', scope,
    [dx_refs(['DX-18','DX-19','DX-21'], 2)])
row(27, 'Preset usa harness_settings vazio, tool_access=ask e grants limitados; modelo/instruções/sandbox não são sobrescritos. Merge preserva customizações e política nativa existente.',
    'Contrato de preservação das opções suportadas verificadas, não certificação de todas as versões/harnesses nem prova de utilidade produtiva. Configuração efetiva não observada fica UNKNOWN no doctor.',
    [dx_refs(['DX-01','DX-13','DX-21'], 1)], source_paths=['src/okto_nexus/application/project_preset.py','src/okto_nexus/application/project_preset_update.py'])
row(28, 'Relatórios mantêm M1 incompleto quando há só serviço/sessão pronta; doctor não confunde initialize/readiness com tarefa, e trabalho terminal sintético é rotulado como tal.',
    'VERIFIED é a preservação da regra de aceite. M1 continua aberto: solicitar/decidir/recuperar no caminho produtivo escolhido e campanhas necessárias não foram executados nesta auditoria.',
    [dx_refs(['DX-07','DX-17','DX-20'], 1)],
    [E+'r3-joint-contracts/milestone.md', E+'pr03-terminal-work.md', E+'pr04-participant-guide/milestone.md'], kind='qualification_honesty')

# Narrow static review of only the new Core production delta, not a new runtime audit.
core_summary = read('docs/evidence/cooperative-drain/summary.json', 'core')
core_delta = []
for entry in core_summary['source_files']:
    if not entry['path'].startswith('src/'):
        continue
    ref = path_ref(entry['path'], 'core')
    assert ref['sha256'] == entry['sha256'], entry['path']
    tree = ast.parse((REPOS['core'] / entry['path']).read_text(encoding='utf-8'))
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(n.name for n in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.append('.' * node.level + (node.module or ''))
    forbidden = [n for n in imports if n.split('.')[0] in {'okto_nexus', 'okto_nexus_connector'}]
    assert not forbidden, (entry['path'], forbidden)
    core_delta.append(dict(ref, imports=sorted(set(imports)), forbidden_application_imports=forbidden))

counts = Counter(r['proposed_status'] for r in rows)
report = dict(format='r3.invariant-reconciliation', version=1, plan=plan_ref, scope=scope,
              method='Finite read-only reconciliation of exactly 28 literal invariants; no product imports, test execution, campaigns or checkout edits.',
              test_runs=0, campaigns_run=0, checkout_edits=False, ledger_edits=False,
              proposal_only=True, status_counts=dict(counts), invariants=rows,
              conditional_acceptance='INV-06/20/21 require final accepted Nexus SVC-07 evidence; do not consume active test reports.',
              global_acceptance='No M1/M2/R3 closure and no platform promotion. INV-12/24/28 are qualification-honesty rules.',
              historical_evidence_rule='Historical passing XML is reused for its specific assertions and original scope, not represented as a new run of current bytes.',
              credential_chain='Actual client parsing/initialize and protected component tests are separate; full OS vault→shipped launcher→real client→canonical cooperation remains NOT_RUN.',
              narrow_core_delta_review=core_delta)

def write(name, obj):
    (OUT/name).write_text(json.dumps(obj, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')

write('matrix.json', report)
write('retained-testcase-checks.json', dict(action='parse retained XML; no pytest execution', selections=checks,
      distinct_passed_identities=len({(c['report']['repository'], c['report']['path'], n) for c in checks for n in c['matched_cases']})))
write('input-manifest.json', dict(files=sorted(inputs.values(), key=lambda x:(x['repository'],x['path'])),
      note='Only explicitly cited public files; no private state, credentials, databases or broad workspace indexing.'))
summary = ['# Reconciliação finita dos 28 invariantes', '',
           f"Proposta: {counts['VERIFIED']} VERIFIED e {counts['CONDITIONAL_PENDING_QUALIFIED']} condicionais. Nenhum status foi alterado.", '',
           'INV-06, INV-20 e INV-21 dependem do fechamento da qualificação Nexus SVC-07. Core/Connector têm evidência instalada própria; ela não substitui Nexus.', '',
           'INV-12, INV-24 e INV-28 podem ser VERIFIED como regras de honestidade. Isso mantém M1/M2/R3 abertos e não executa nem promove login, reboot, provedor ou cadeia completa de cofre→cliente.', '',
           'A matriz contém texto literal, linha do plano, fonte atual com SHA, testes/assertions e XML retidos, limite e motivo por ID. O parser validou os PASS citados; não rodou testes.', '',
           '| ID | Proposta | Fundamento |', '|---|---|---|']
for r in rows:
    summary.append('| '+r['id']+' | '+r['proposed_status']+' | '+r['reason'].replace('|','\\|')+' |')
summary += ['', 'Limites comuns: Windows/local; pares sintéticos; provas históricas não se tornam reexecuções do código atual. Auditoria de import do Core 5721 permanece histórica; apenas imports do delta Core 140701 foram conferidos estaticamente.', '',
            'A leitura não encontrou lacuna concreta adicional de produto nesses contratos. As três entradas condicionais são de qualificação em andamento, não uma declaração de falha. O parent decide a aplicação das recomendações e o aceite da evidência final.']
(OUT/'summary.md').write_text('\n'.join(summary)+'\n',encoding='utf-8')
allowlist = ['matrix.json','summary.md','input-manifest.json','retained-testcase-checks.json','reconcile.py']
write('artifact-manifest.json', dict(public_allowlist=allowlist, files=[dict(path=n,sha256=digest((OUT/n).read_bytes()),bytes=(OUT/n).stat().st_size) for n in allowlist],
      excludes=['private state','credentials','DB','venv','raw runtime responses'], executions='none; script only reads public artifacts and writes this Temp directory'))
print(json.dumps(dict(output=str(OUT), counts=dict(counts), inputs=len(inputs), xml_selections=len(checks),
      matrix_sha256=digest((OUT/'matrix.json').read_bytes()), manifest_sha256=digest((OUT/'artifact-manifest.json').read_bytes())),indent=2))
