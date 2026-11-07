"""Collect only closed public reports/patches. Never collect fixture DBs or vaults."""
from __future__ import annotations

import ast
import difflib
import hashlib
import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
ROOT = Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
SNAPSHOT = 'af056bb10d1c1a8602bbeb64a4be352918834a84'
NEW = 'tests/execution_r4/test_r3_mixed_coordination.py'
REMOTE = 'tests/execution_r4/test_remote_connection.py'
PLAN_SHA = '20d0fafdedc793b97a277f5d41355d7d597ff724a77687394215eea3113ba996'

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def function_ref(relative, name, *, isolated=False):
    path = (HERE / 'isolated' if isolated else ROOT) / relative
    raw = path.read_bytes()
    tree = ast.parse(raw)
    fn = next(n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name)
    return {'path': relative, 'function': name, 'line': fn.lineno, 'last_line': fn.end_lineno,
            'file_sha256': hashlib.sha256(raw).hexdigest(),
            'source': 'outside-checkout candidate' if isolated else SNAPSHOT}

def report(path):
    root = ET.parse(path).getroot()
    cases = []
    for case in root.iter('testcase'):
        identity = case.get('classname', '').removeprefix('tests.') + '::' + case.get('name', '')
        status = ('failed' if case.find('failure') is not None or case.find('error') is not None
                  else 'skipped' if case.find('skipped') is not None else 'passed')
        cases.append({'identity': identity, 'status': status})
    return {'path': str(path), 'sha256': digest(path), 'cases': cases,
            'counts': {kind: sum(c['status'] == kind for c in cases) for kind in ('passed', 'failed', 'skipped')}}

historical = []
for name in ('ns06-05-consumption-r4.xml', 'ns06-05-combined-r4.xml',
             'r4-053-full/tests.xml', 'vault-fixed-r4-campaign/tests.xml'):
    path = ROOT / 'plans/r4_execution/evidence' / name
    item = report(path)
    item['path'] = path.relative_to(ROOT).as_posix()
    item['matching_rg11_cases'] = [c for c in item.pop('cases') if
        'test_canonical_push_reservation_excludes_mcp_pull' in c['identity'] or
        'test_remote_domain_delivery_keeps_exclusive_claim_from_mcp' in c['identity']]
    item['scope'] = 'Historical report, not a rerun of current installed payload; matching assertions were inspected in current source separately.'
    historical.append(item)

attempts = []
for name in ('initial', 'diagnostic', 'final', 'rg11-current', 'rg11-remote-final', 'rg11-shared-fixture-final'):
    folder = HERE / 'reports' / name
    assert (folder / 'qualification.json').is_file(), f'Attempt still running or unqualified: {name}'
    item = report(folder / 'tests.xml')
    item['path'] = (folder / 'tests.xml').relative_to(HERE).as_posix()
    item['attempt'] = name
    item['qualification'] = (folder / 'qualification.json').relative_to(HERE).as_posix()
    item['qualification_sha256'] = digest(folder / 'qualification.json')
    attempts.append(item)

latest = {}
for attempt in attempts:
    for case in attempt['cases']:
        latest[case['identity']] = {**case, 'report': attempt['path']}
assert len(latest) == 9
assert {c['status'] for c in latest.values()} == {'passed'}

candidate = HERE / 'isolated' / NEW
new_patch = ''.join(difflib.unified_diff([], candidate.read_text(encoding='utf-8').splitlines(keepends=True),
                                     fromfile='/dev/null', tofile='b/' + NEW))
(HERE / 'new-tests.patch').write_text(new_patch, encoding='utf-8')
old_remote = HERE / 'reports/rg11-current/remote-fixture-original.py'
new_remote = HERE / 'isolated' / REMOTE
fixture_patch = ''.join(difflib.unified_diff(old_remote.read_text(encoding='utf-8').splitlines(keepends=True),
                                         new_remote.read_text(encoding='utf-8').splitlines(keepends=True),
                                         fromfile='a/' + REMOTE, tofile='b/' + REMOTE))
assert fixture_patch == (HERE / 'fixture.patch').read_text(encoding='utf-8')
(HERE / 'candidate.patch').write_text(new_patch + fixture_patch, encoding='utf-8')
for relative in (NEW, REMOTE):
    target = HERE / 'candidate' / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(HERE / 'isolated' / relative, target)

new_rg01 = function_ref(NEW, 'test_rg01_two_mcp_participants_and_one_runtime_cooperate_without_new_identities', isolated=True)
new_rg02 = function_ref(NEW, 'test_rg02_broadcast_mcp_and_managed_runtime_have_one_claim_and_effect', isolated=True)
matrix = {
 'format':'okto.r3.safe-rg-map', 'version':1,
 'published_nexus_snapshot':SNAPSHOT, 'fixed_plan_sha256':PLAN_SHA,
 'scope':'Fixed RG-01/RG-02/RG-11 only. Candidate tests and one shared fixture correction outside checkout; no product/ledger edit or global acceptance promotion.',
 'installed_artifacts': {
  'nexus': {'version':'0.3.3','sha256':'9b18dc0c69673bb730198ca461f2464c8ee4ae3fdc1226f22ffcb8140783412f'},
  'connector': {'version':'0.0.12','sha256':'a8cf18105fa1cdca0443b6a3be08972d5576f72f3ce07e5a19dd9fc7cd59ae5a'},
  'core': {'version':'0.0.14','sha256':'5721e462add21d65380f070a68db07a653a498a78d4be9ea0cf949909d3cfecb'},
  'interpreter':'C:/Users/jpamb/AppData/Local/Temp/nexus-ci-connector-refresh-la1tb1l6/venv/Scripts/python.exe',
  'mcp':'1.30.0', 'authority':'Existing clean CI qualification selected by root; this audit additionally guards loaded module origins in every executed test. Shared environment is never modified.',
 },
 'mapping': [
  {'id':'RG-01', 'requirement':'Dois participantes MCP e um runtime gerenciado cooperam no mesmo workspace sem identidades duplicadas.',
   'existing_inspected':[function_ref('tests/execution_r4/test_handoff_ordinary_fanout.py','test_ordinary_broadcast_reaches_two_runtimes_and_mcp_but_direct_handoff_only_one')],
   'existing_exact_assertions':['The old case creates two managed runtimes and one MCP-only actor; checks two native sends, distinct recipient claims and an unconsumed MCP delivery row. It is the reverse population and does not demonstrate two MCP participants exchanging work with one runtime.'],
   'retained_result_limit':'No exact test-name match for ordinary_fanout was found in retained plans XMLs; no fabricated passing result is inferred.',
   'candidate':new_rg01,
   'candidate_assertions':['Two separately authenticated canonical MCP actors open their sessions in one workspace.', 'MCP caller sends to MCP peer; peer pulls/acks then sends to the managed subject.', 'Synthetic native terminal event flows through actual Core receipt and canonical runtime-result publication; peer pulls that exact reply and sends a correlated response to caller.', 'Agent IDs before/after are identical; one binding/session/turn/native send and one delivery per tracked message; canonical result parent, sender and workspace are exact.', 'Foreign-key consistency and canonical runtime close are asserted.'],
   'qualified_result':'1 current installed passing identity; actual ASGI HTTP/MCP/SQLite/application/Core, explicit synthetic native I/O.',
   'not_claimed':'Not two real external client binaries, actual provider work, real TCP for this new local fixture, or AC-03/M1/M2 acceptance.'},
  {'id':'RG-02', 'requirement':'Broadcast handoff disputado por MCP/runtime continua com um único vencedor.',
   'existing_inspected':[function_ref('tests/execution_r4/test_canonical_consumption.py','test_handoff_pull_and_runtime_compete_for_one_claim'), function_ref('tests/execution_r4/test_canonical_handoff.py','prepare'), function_ref('tests/execution_r4/test_canonical_admission_races.py','test_competitive_handoff_pool_has_one_executor_across_agents_and_bindings'), function_ref('tests/execution_r4/test_handoff_broadcast_scale.py','test_hundred_runtime_candidates_have_one_winner_and_no_loser_native_invocation')],
   'existing_exact_assertions':['Mixed pull/runtime test uses a DIRECT target from prepare, not broadcast.', 'Current old pull helper sends idempotency_key without runtime_endpoint_id; that option is managed-only. Its historical passing result cannot prove both current contenders are valid.', 'Other inspected races compare only managed candidates (role target or 100 runtime broadcast candidates), not a MCP pull contender.'],
   'candidate':new_rg02,
   'candidate_assertions':['Actual handoff_create uses target.strategy=broadcast, not a mutated row or role/direct target.', 'One regular MCP actor competes with a separately authorized managed subject using current canonical call shapes.', 'MCP-first and runtime-first each prove that specific valid actor wins; concurrent case starts both through a barrier.', 'Exactly one claim event, claimed_by and epoch=1; only the managed winner may create one runtime binding/turn/outbox or charge one work grant.', 'Losing retry stays refused; no identity duplication; native opens/sends equal the managed-winning indicator.'],
   'qualified_result':'3 current installed passing identities after fixing a test-only invalid MCP managed option.',
   'not_claimed':'No new scheduler, fairness target, provider, native service or global R3 acceptance.'},
  {'id':'RG-11', 'requirement':'Mesmo agente com MCP externo e runtime gerenciado mantém uma entrega lógica exclusiva, sem fan-out involuntário por canal.',
   'existing_inspected':[function_ref('tests/execution_r4/test_canonical_consumption.py','test_canonical_push_reservation_excludes_mcp_pull'), function_ref('tests/execution_r4/test_remote_connection.py','test_remote_domain_delivery_keeps_exclusive_claim_from_mcp'), function_ref('tests/execution_r4/test_remote_connection.py','test_owned_connector_reader_dispatches_five_actions_over_real_websocket')],
   'existing_exact_assertions':['Local admitted/accepted/terminal/closed: same subject MCP pull returns empty twice; consumer_kind/operation/attempts remain unchanged; one outbox and one turn; one native open/send.', 'Remote wrapper passes domain_delivery=True. That branch creates one push claim/domain-delivery, and same subject MCP inbox_pull returns empty; owned reader uses actual loopback HTTP/WebSocket and synthetic native factory.', 'The broad remote fixture also exercises steer/interrupt/close; those are not additional deliveries and are not counted as duplicate native sends.'],
   'historical_reports':[h['path'] for h in historical],
   'qualified_result':'5 current installed passing identities: four unchanged local phases plus remote wrapper with explicit manual-lifecycle fixture generation.',
   'new_test_needed':False,
   'not_counted':{'source':function_ref('tests/execution_r4/test_combined_consumption.py','verify_competition'), 'reason':'Strong assertions exist in this helper, but no current invocation supplies non-null combined_winner. Historical test_ns06_05 case names without retained wrapper bytes do not establish its exact invocation. Not used as proof.'},
   'not_claimed':'Actual external MCP binary or real provider behavior; no need to require embedded+remote runtimes simultaneously for this literal same-agent MCP/runtime criterion.'},
 ],
 'historical_reports':historical,
 'current_attempts':attempts,
 'latest_unique_cases':list(latest.values()),
 'current_qualified_unique_count':9,
 'new_case_count':4, 'reused_case_count':5,
 'overlap_policy':'Initial, diagnostic and repeated remote fixture attempts are retained separately; latest passing identities replace previous results without adding to 9.',
 'initial_findings':[
  {'attempts':['initial','diagnostic'],'classification':'candidate_test_input_error','detail':'MCP pull claim incorrectly supplied managed-only idempotency_key, causing VALIDATION_ERROR before competition. Removed from that contender only; both deterministic orderings then pass. Runtime-first/concurrent passes before correction are not relied upon as valid mixed-race proof.'},
  {'attempts':['rg11-current'],'classification':'legacy_fixture_lifecycle_omission','detail':'The remote helper constructs DaemonApp and controls components manually, never entering run_forever; shutdown.json now needs service_generation. Business assertions completed before cleanup AttributeError. Product/public startup already sets generation before waiting/shutdown.'},
  {'attempts':['rg11-remote-final','rg11-shared-fixture-final'],'classification':'fixture_correction_and_consolidation','detail':'First confirmed the isolated shutdown-generation diagnosis. Final shared patch supplies separate 32-hex synthetic generations after both manual DaemonApp constructions; final remote case passes unchanged production. No shutdown call/assertion is bypassed.'},
 ],
 'fixture_patch':{'path':'fixture.patch','sha256':digest(HERE/'fixture.patch'), 'final_file_sha256':digest(new_remote), 'scope':'Only synthetic service_generation values and comments after the two existing manual constructions; no lifecycle capability or readiness claim.'},
 'new_tests_patch':{'path':'new-tests.patch','sha256':digest(HERE/'new-tests.patch'),'final_file_sha256':digest(candidate)},
 'combined_patch':{'path':'candidate.patch','sha256':digest(HERE/'candidate.patch')},
 'lint':{'command':'rtk proxy ruff check <candidate test> --output-format json --output-file ruff-final.json','new_test_full_check':'passed','diagnostics':json.loads((HERE/'ruff-final.json').read_text()),'existing_helper':'Only assignments/comments changed; inherited whole-file lint is not represented as clean.'},
 'boundaries':[
  'No checkout or ledger edits; no commit/push; candidate patch is for root review/application.',
  'No shared venv change. -I, isolated cwd and USERPROFILE/APPDATA/LOCALAPPDATA, cleared application/provider environment before imports; only fixture-generated credentials in disposable approved file vault.',
  'No provider executable or registered native service. Existing synthetic inventory and native factories are reused; no new authority/readiness bypass introduced.',
  'New local tests use the actual ASGI application/MCP mount, not a network socket. The reused remote test uses real loopback HTTP/WebSocket.',
  'Private fixture homes/databases/vaults/bearer material are excluded from public manifest. They are not hashed or copied into the candidate evidence.',
  'No real-client/M1/M2/native-platform/global acceptance promotion follows from these fixture contracts.',
 ],
}
(HERE/'mapping.json').write_text(json.dumps(matrix,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

nodes = [NEW,
 'tests/execution_r4/test_canonical_consumption.py::test_canonical_push_reservation_excludes_mcp_pull',
 'tests/execution_r4/test_remote_connection.py::test_remote_domain_delivery_keeps_exclusive_claim_from_mcp']
(HERE/'qualification-nodes.json').write_text(json.dumps({'nodes':nodes,'expected_case_count':9,'new_cases':4,'existing_cases':5},indent=2)+'\n',encoding='utf-8')
text = '''# SAFE-RG: RG-01, RG-02 e RG-11

Snapshot Nexus `af056bb10d1c1a8602bbeb64a4be352918834a84`; plano R3 inalterado. Tudo foi preparado em Temp, sem editar checkout ou ledger.

**Resultado: 9 identidades qualificadas no pacote instalado atual — quatro novas e cinco reaproveitadas.** Não são nove testes novos nem soma dos reruns. Nexus 9b18…, Connector a8cf… e Core 5721…, MCP 1.30.0; imports ficaram na venv CI qualificada. Os XMLs iniciais permanecem separados.

| Cenário | Mapeamento exato | Resultado atual |
|---|---|---|
| RG-01 | O teste antigo tinha dois runtimes e um MCP, sem comprovar a população pedida. Novo teste usa dois atores MCP autenticados e um runtime no mesmo workspace; troca mensagens, publica a resposta nativa canônica, verifica referências e ausência de novas identidades. | 1 passou |
| RG-02 | A disputa antiga era DIRECT; as outras disputas inspecionadas eram somente entre runtimes. Novo teste cria BROADCAST real e compara MCP-primeiro, runtime-primeiro e corrida, verificando um claim/epoch/efeito e nenhuma cobrança do perdedor. | 3 passaram |
| RG-11 | Reaproveitados os quatro estados de exclusão push→MCP e o caso remoto HTTP/WSS. Mesma identidade, pull vazio, claim persistido, uma entrega/turno. Nenhum teste redundante novo. | 5 passaram |

O helper `verify_competition` tem assertions fortes, mas não possui invocação atual com `combined_winner` não nulo; não foi contado como evidência. Os resultados históricos reaproveitáveis e hashes estão em `mapping.json`.

## Correções de fixture e relatórios

- Candidato inicial: 3 passaram e 1 falhou. O claim MCP enviava `idempotency_key`, opção somente do claim gerenciado; rodada diagnóstica confirmou VALIDATION_ERROR. Remover essa opção tornou ambos os lados elegíveis. A rodada final passou 4/4.
- RG-11 inicial atual: quatro locais passaram; remoto concluiu as assertions funcionais, mas cleanup falhou por `service_generation` ausente. O helper liga componentes manualmente sem entrar em `run_forever`, que cria esse campo no fluxo público.
- `fixture.patch` adiciona apenas generation sintética 32-hex após as duas construções manuais, com valores distintos. Mantém `_shutdown` e suas assertions. A correção foi compartilhada com o reviewer de RG-04. O remoto passou após o ajuste intermediário e novamente nos bytes finais compartilhados.
- Ruff integral do novo arquivo passou. O lint global preexistente do helper antigo não é declarado limpo.

## Entrega

- `candidate.patch`: arquivo novo + correção mínima do helper.
- `new-tests.patch` e `fixture.patch`: partes separadas para revisão.
- `candidate/tests/execution_r4/`: bytes finais dos dois arquivos.
- `qualification-nodes.json`: seleção de nove casos para eventual integração final.
- `mapping.json`: assertions, localização/sha dos arquivos, resultados históricos, tentativas atuais e limites.
- `artifact-manifest.json`: allowlist pública com hashes. Não inclui homes, DBs, vaults ou bearers de fixture.

Os novos casos usam HTTP/MCP via ASGI real, SQLite e Core, com I/O nativo sintético. O caso remoto reaproveitado usa HTTP/WSS loopback real. Isso qualifica os contratos destes RG, não dois binários MCP reais, provedor, serviço nativo, M1/M2 ou aceite global R3.
'''
(HERE/'mapping.md').write_text(text,encoding='utf-8')

(HERE/'reproduce.md').write_text('''# Reproduzir a proposta isolada

Não aplicar nem executar estes comandos automaticamente. A árvore pública é uma allowlist de evidências, não contém as homes privadas usadas nos testes.

1. Criar novo diretório Temp. Exportar somente `tests` e `plans/contratos` do commit Nexus `af056bb10d1c1a8602bbeb64a4be352918834a84` com `rtk proxy git archive --format=zip --output=<arquivo> <commit> tests plans/contratos`; extrair em `<Temp>/isolated`.
2. Aplicar `candidate.patch` nessa cópia (`rtk proxy git apply --check`, depois `git apply` apenas quando autorizado). Ele adiciona um teste e cinco linhas ao helper existente. As cópias finais em `candidate/` permitem conferir bytes.
3. Em `isolated/pytest.ini`, usar `[pytest]`, `asyncio_mode = auto` e `testpaths = tests`. Não apontar pythonpath ao checkout.
4. Usar ambiente novo com as wheels exatas e dependências resolvidas declaradas em `mapping.json`, ou a venv CI qualificada em modo somente leitura. Não modificar uma venv compartilhada. O runner exige `-I`, versões corretas, imports instalados e perfis descartáveis.
5. Executar `rtk proxy <python-qualificado> -I <Temp>/run_candidate.py <nome-inédito> <nodes>`; os nodes exatos estão em `qualification-nodes.json`. Cada tentativa escreve XML/qualification novos e nunca sobrescreve tentativa anterior.

Os comandos executados estão nos `reports/*/invocation.json`; a seleção nova produziu quatro casos e RG-11 mais cinco. Os erros iniciais e a correção da fixture estão mapeados. Não copiar DBs, WAL/SHM, vaults, perfis ou bearers para evidência pública; manter os limites sintéticos e não chamar isso de campanha de provedor/serviço nativo.
''',encoding='utf-8')

public = [HERE/name for name in ('build_map.py','run_candidate.py','mapping.json','mapping.md','reproduce.md','candidate.patch','fixture.patch','new-tests.patch','qualification-nodes.json','ruff-final.json')]
public += [HERE/'candidate'/name for name in (NEW,REMOTE)]
for item in attempts:
    folder = HERE/'reports'/item['attempt']
    public += [folder/name for name in ('tests.xml','invocation.json','qualification.json')]
    public += [p for p in folder.glob('*.py')]
manifest = {'format':'okto.r3.safe-rg-public-artifacts','version':1,'source_snapshot':SNAPSHOT,'plan_sha256':PLAN_SHA,
            'files':{p.relative_to(HERE).as_posix():{'sha256':digest(p),'bytes':p.stat().st_size} for p in public},
            'excluded':['fixture-source.zip','isolated/ copied fixture tree','reports/*/profile','reports/*/pytest-home','all SQLite/WAL/SHM/vault/bearer files']}
(HERE/'artifact-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'output':str(HERE),'unique_current_passed':len(latest),'new':4,'reused':5,
                  'new_test_sha256':digest(candidate),'fixture_sha256':digest(new_remote),
                  'mapping_sha256':digest(HERE/'mapping.json'),'manifest_sha256':digest(HERE/'artifact-manifest.json')},indent=2))
