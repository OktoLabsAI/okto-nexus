from pathlib import Path
import hashlib
import json
import re
import shutil
import zipfile
import xml.etree.ElementTree as ET

ROOT = Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
TEMP = Path('C:/Users/jpamb/AppData/Local/Temp')
OUT = ROOT / 'plans/agent_ops/evidence/r3-joint-contracts'
assert not OUT.exists()
def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(p, data):
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')

groups = [
    ('mixed', 'r3-safe-rg-mixed-qvb51fg9', 'artifact-manifest.json'),
    ('idle', 'r3-rg03-idle-7kvw51zk', 'manifest.json'),
    ('sessions-initial', 'r3-rg04-installed-9h8px6xo', 'manifest.json'),
    ('sessions-retest', 'r3-rg04-remote-retest-3kxmt936', 'manifest.json'),
]
sources = []
for dest, folder, manifest in groups:
    base = TEMP / folder / 'public'
    data = json.loads((base/manifest).read_text(encoding='utf-8'))
    if 'artifacts' in data:
        files = {x['path']: x['artifact_sha256'] for x in data['artifacts']}
    else:
        files = {k: v['sha256'] for k,v in data.get('files', data).items()}
    assert set(files) | {manifest} == {p.relative_to(base).as_posix() for p in base.rglob('*') if p.is_file()}
    for name, expected in files.items():
        assert sha(base/name) == expected, (folder,name)
    for name in [*files, manifest]:
        sources.append((base/name, OUT/dest/name))

for name in ['reports.json','selection.json','ci-runner.log','ci-runner.json','ci/installed.json','ci/campaign.json','ci/tests.xml','launch.py','run_redacted.py']:
    sources.append((TEMP/'r3-rg05-current-9j7cz3cz'/name, OUT/'recovery'/name))
for name in ['audit.py','observation.json','application-import-boundaries.json']:
    sources.append((TEMP/'r3-core-current-audit-dth2i_fh'/name, OUT/'core'/name))

# Public allowlist only. Reject credential-shaped literals; do not print matches.
pattern = re.compile(rb'\b(?:nxs_|nxobs_|nxsept_|nxt4_|nxc4_)[A-Za-z0-9_-]{20,}')
for src, dst in sources:
    assert not pattern.search(src.read_bytes()), f'credential-shaped literal: {src.name}'
    assert src.suffix not in {'.db','.sqlite','.sqlite3','.zip','.whl'}
for src, dst in sources:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)

expected_tests = {
    'test_r3_mixed_coordination.py':'22f7b5b4af430f2226f135c1744b3792969acd4c9d60f6ed0d9880bf495e8b22',
    'test_remote_connection.py':'d74ca53fc282cce450f010260bc38c534445fa8b2a98fa561fa93259d524255d',
    'test_external_idle_scheduler_isolation.py':'ae9597ae5470cd8ba41492861e332e633508637475ad44cf320d36b5190cb02d',
}
for name, expected in expected_tests.items():
    assert sha(ROOT/'tests/execution_r4'/name) == expected

qualified = {}
attempts = [
    ('mixed/reports/final/tests.xml',4),
    ('mixed/reports/rg11-current/tests.xml',4),
    ('mixed/reports/rg11-shared-fixture-final/tests.xml',1),
    ('idle/rg03-qualified.xml',6),
    ('sessions-initial/reports/tests.xml',16),
    ('sessions-retest/reports/tests.xml',1),
    ('recovery/ci/tests.xml',39),
]
for path, count in attempts:
    cases = ET.parse(OUT/path).getroot().findall('.//testcase')
    passed = [x for x in cases if not any(x.find(k) is not None for k in ('failure','error','skipped'))]
    assert len(passed) == count, (path,len(passed))
    for case in passed:
        key = case.attrib['classname']+'::'+case.attrib['name']
        assert key not in qualified, key
        qualified[key] = path
assert len(qualified) == 71

wheel = TEMP/'dx04-mcp-guide-installed-sk13m28a/candidate-v1/wheels/okto_nexus-0.3.3-py3-none-any.whl'
assert sha(wheel) == '9b18dc0c69673bb730198ca461f2464c8ee4ae3fdc1226f22ffcb8140783412f'
installed = TEMP/'nexus-ci-connector-refresh-la1tb1l6/venv/Lib/site-packages'
with zipfile.ZipFile(wheel) as archive:
    package = [n for n in archive.namelist() if n.startswith('okto_nexus/') and not n.endswith('/')]
    assert len(package) == 690
    for name in package:
        assert archive.read(name) == (ROOT/'src'/name).read_bytes() == (installed/name).read_bytes(), name
dump(OUT/'integration.json', dict(
    source_base='af056bb10d1c1a8602bbeb64a4be352918834a84',
    unique_passed_cases=71, case_reports=qualified, exact_test_sha256=expected_tests,
    nexus_wheel_sha256=sha(wheel), source_wheel_installed_equal_files=690,
    connector_wheel_sha256='a8cf18105fa1cdca0443b6a3be08972d5576f72f3ce07e5a19dd9fc7cd59ae5a',
    core_wheel_sha256='5721e462add21d65380f070a68db07a653a498a78d4be9ea0cf949909d3cfecb',
    mcp_version='1.30.0', dependency_solve_evidence='../r3-qualification-readiness/ci/reports.json',
    product_changed=False, public_source_files=len(sources),
    credential_literal_scan='No matching credential-shaped literals; allowlist excludes runtime homes, databases and vaults.',
    limitations=['Canonical Windows contracts with synthetic native peers; not actual MCP client/provider qualification.',
                 'RG-05 covers 39 named recovery cases, not every new path.',
                 'Core audit does not instrument arbitrary environment lookups or native credential APIs; stdout summary is manually retained.',
                 'No native OS service registration or real-provider campaign; no full M1/M2 or global acceptance.']))

summary = '''# R3 — contratos conjuntos no pacote instalado

71 identidades únicas aprovadas: RG-01/02/11 (9), RG-03 (6), RG-04 (17) e recuperação selecionada RG-05 (39). Dez casos são novos; os demais reutilizam testes existentes. Reruns e rodadas iniciais não são somados. `integration.json` liga cada identidade ao XML de aprovação.

Os testes usam os wheels atuais Nexus 0.3.3, Connector 0.0.12 e Core 0.0.14 com MCP 1.30.0 na venv CI isolada cuja resolução e `pip check` estão retidos em `../r3-qualification-readiness/ci/reports.json`. Os 690 arquivos do pacote Nexus continuam byte a byte iguais entre checkout, wheel e instalação; não houve alteração de produto.

RG-01 valida dois participantes MCP autenticados e um runtime no mesmo workspace, mensagens e resultado canônico sem duplicação. RG-02 disputa BROADCAST com MCP primeiro, runtime primeiro e corrida; há um vencedor/epoch/efeito. RG-03 preserva prioridade, FIFO, fairness, opt-in, audiência e reserva Core durante observação idle; TTL diminui sem renovação. RG-04 mantém shared/per_sender/per_sender_session/one_shot. RG-11 mantém entrega exclusiva entre push runtime e pull MCP, incluindo HTTP/WSS loopback.

As duas construções manuais de DaemonApp na fixture remota recebem gerações sintéticas distintas para seu recibo de shutdown. O fluxo público atribui isso em run_forever, que a fixture não executa. Shutdown e assertions permanecem ativos. Não foi demonstrado defeito do Connector.

Falhas iniciais permanecem preservadas: parâmetro idempotency_key indevido no claim MCP; comparação do TTL remanescente como constante; cleanup da fixture sem generation. Imports de fixture foram ajustados para Ruff e os seis casos RG-03 requalificados nos bytes finais. Os dois arquivos novos passam Ruff integral; não se declara lint global limpo do helper antigo.

RG-05 permanece em progresso: 39 casos verificam recuperação sem replay para work/decision, participant init/launch, coordenação/cooperação, bootstrap remoto e Finish. Doubles e fronteiras reais estão discriminados em recovery/reports.json; não certificam todos os caminhos ou quedas reais de serviços/provedores.

RG-06 permanece em progresso: 131 módulos Core atuais importados sob guards sem eventos negados; arquivos de origem/wheel/instalação iguais. O resumo observado é manual, sem stdout bruto local; não cobre qualquer leitura de ambiente nem API nativa de credenciais. AST literal de 513 arquivos Nexus e 122 Connector não encontrou import entre aplicações; essa verificação das aplicações não cobre imports dinâmicos. Auditoria em core/.

RG-01/02/03/04/11 ficam verificados no escopo canônico Windows com peers nativos sintéticos. Não são dois executáveis MCP reais, inferência de provedor, serviço registrado, M1/M2 ou aceite global R3. RG-07, rastreabilidade final, revisão de artefatos e campanhas reais continuam abertos. O plano fixo e seus conjuntos de 59/132/28/17 IDs permanecem iguais.

Somente arquivos públicos enumerados foram copiados; homes, bancos, cofres e tokens de fixture ficaram fora. Manifests originais e falhas históricas são imutáveis. O manifesto deste diretório conserva hashes exatos.
'''
(OUT/'milestone.md').write_text(summary,encoding='utf-8')
shutil.copyfile(__file__,OUT/'close-milestone.py')
manifest={p.relative_to(OUT).as_posix():dict(sha256=sha(p),bytes=p.stat().st_size) for p in sorted(OUT.rglob('*')) if p.is_file()}
dump(OUT/'artifact-manifest.json',dict(format='r3-joint-contracts-v1',files=manifest))

ledger_path=ROOT/'plans/agent_ops/ledger.json'
ledger=json.loads(ledger_path.read_text(encoding='utf-8'))
assert hashlib.sha256((ROOT/ledger['plan']).read_text(encoding='utf-8').encode()).hexdigest()==ledger['plan_sha256']=='20d0fafdedc793b97a277f5d41355d7d597ff724a77687394215eea3113ba996'
original_sets={k:set(ledger[k]) for k in ('tasks','scenarios','invariants','completion_criteria')}
prefix='plans/agent_ops/evidence/r3-joint-contracts/'
evidence=[prefix+x for x in ('milestone.md','integration.json','artifact-manifest.json')]
for key in ['RG-01','RG-02','RG-03','RG-04','RG-11']:
    row=ledger['scenarios'][key]
    row.update(status='VERIFIED',result='Qualified current installed Windows canonical contract with real SQLite/Core and synthetic native peers. Exact assertions, identities, attempts and limitations retained in the joint milestone; no real-client/provider or global acceptance claim.')
    row['evidence']=sorted(set(row['evidence']+evidence))
for key, scope, extra in [('RG-05','selected_39_current_recovery_cases','recovery/reports.json'),('RG-06','current_131_core_imports_and_literal_application_boundaries','core/observation.json')]:
    row=ledger['scenarios'][key]
    row['status']='IN_PROGRESS'
    row.setdefault('subscopes',{})[scope]='VERIFIED'
    row['evidence']=sorted(set(row['evidence']+evidence+[prefix+extra]))
ledger['milestones']['PR-10']['evidence']=sorted(set(ledger['milestones']['PR-10']['evidence']+evidence))
ledger['campaigns']['r3_joint_installed_contracts']=dict(status='VERIFIED',unique_cases=71,new_cases=10,product_changed=False,scope='Windows canonical contracts, synthetic native peers; no global acceptance',evidence=evidence)
ledger['history'].append(dict(date='2026-11-07',milestone='PR-10',status='IN_PROGRESS',summary='71 unique installed cases passed: 9 mixed delivery, 6 idle isolation, 17 session modes and 39 selected recovery. Ten new tests and a manually owned remote fixture generation fix; no product change. RG-01/02/03/04/11 verified at canonical Windows contract scope; RG-05/06 remain in progress. Current Core import audit is narrowly scoped and honestly retains only an observed stdout summary. Full M1/M2, compatibility, final trace/public artifact review and real campaigns remain open.',evidence=evidence))
ledger['updated_at']='2026-11-07'
assert original_sets=={k:set(ledger[k]) for k in original_sets}
dump(ledger_path,ledger)
for name in ['LEDGER_CODEX_NEXUS_INTEGRACAO_ATENCAO_ONBOARDING.md','plans/agent_ops/implementation-report.md']:
    with (ROOT/name).open('a',encoding='utf-8') as stream:
        stream.write('\n\n## 2026-11-07 — R3: contratos conjuntos instalados\n\n71 casos únicos passaram: 9 de coordenação/entrega mista, 6 de isolamento idle, 17 de modos de sessão e 39 de recuperação selecionada. Dez casos novos e correção mínima da geração da fixture remota; aplicações e wheels inalterados. RG-01/02/03/04/11 verificados no escopo canônico Windows com peers sintéticos. RG-05/06 permanecem em progresso; import audit Core cobre 131 módulos com limites explícitos. Não há promoção de M1/M2 ou aceite global. Evidências e tentativas iniciais: `plans/agent_ops/evidence/r3-joint-contracts/milestone.md` e manifesto adjacente. Compatibilidade, rastreabilidade/revisão pública final e campanhas reais continuam pendentes.\n')
with (ROOT/'.gitattributes').open('a',encoding='utf-8') as stream:
    stream.write('# Joint installed-contract reports retain their original qualification bytes.\nplans/agent_ops/evidence/r3-joint-contracts/** -text -whitespace\n')
print(json.dumps(dict(artifacts=len(manifest),qualified=len(qualified),new_cases=10,package_files=len(package),manifest_sha256=sha(OUT/'artifact-manifest.json'))))
