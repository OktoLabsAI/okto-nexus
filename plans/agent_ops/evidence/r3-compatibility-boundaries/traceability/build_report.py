"""Assemble a finite traceability review, without changing product or ledger."""
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
OUT = Path(__file__).parent
E = 'plans/agent_ops/evidence/'
BASE = '5545dbde'

def sha(data):
    return hashlib.sha256(data).hexdigest()

def frozen(p):
    return subprocess.check_output(['rtk', 'proxy', 'git', '-C', str(ROOT), 'show', f'{BASE}:{p}'])

def local(p):
    return json.loads((OUT / p).read_text(encoding='utf-8'))

ledger = json.loads(frozen('plans/agent_ops/ledger.json'))
plan = frozen('PLANO_CODEX_NEXUS_INTEGRACAO_ATENCAO_ONBOARDING.md').decode('utf-8')
prior = json.loads(frozen(E+'r3-qualification-readiness/audit/completion-matrix.json'))
verification = local('verification.json')
protection = local('protection-tests.json')
supplement = local('supplemental-checks.json')
payload = local('payload-verification.json')
# Clarify the data-only nature of the comparison without rerunning it.
payload['method'] = 'Read-only bytes of existing wheel, current source and CI installation; no product imports or product process launched.'
(OUT/'payload-verification.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

catalog = {
    'joint': E+'r3-joint-contracts/integration.json',
    'joint_scope': E+'r3-joint-contracts/milestone.md',
    'current_dependencies': E+'r3-qualification-readiness/ci/reports.json',
    'current_package': E+'pr04-participant-guide/installed/candidate-v1/package-proof.json',
    'ci_installed': E+'r3-qualification-readiness/ci/ci/installed.json',
    'core_import_scope': E+'r3-joint-contracts/core/observation.json',
    'application_boundaries': E+'r3-joint-contracts/core/application-import-boundaries.json',
    'mixed_isolation': E+'r3-joint-contracts/mixed/run_candidate.py',
    'mixed_installed': E+'r3-joint-contracts/mixed/reports/final/qualification.json',
    'sessions_isolation': E+'r3-joint-contracts/sessions-initial/run.py',
    'sessions_invocation': E+'r3-joint-contracts/sessions-initial/invocation.json',
    'idle_scope': E+'r3-joint-contracts/idle/report.json',
    'idle_runner': E+'r3-joint-contracts/idle/run_redacted.py',
    'recovery_scope': E+'r3-joint-contracts/recovery/reports.json',
    'recovery_runner': E+'r3-joint-contracts/recovery/run_redacted.py',
    'guide': E+'pr04-participant-guide/milestone.md',
    'guide_server_driver': E+'pr04-participant-guide/installed/drivers/servers.py',
    'bootstrap': E+'pr03-remote-bootstrap.md',
    'bootstrap_tests': E+'pr03-remote-bootstrap/candidate-v1/nexus/installed.xml',
    'renewal': E+'pr03-remote-renewal.md',
    'participant_tests': E+'pr04-participant-removal-installed.xml',
    'observer_tests': E+'pr09-herdr/installed/qualified-v2/pr09-observation-installed-v2-initial.xml',
    'herdr': E+'pr09-herdr.md',
    'herdr_manifest': E+'pr09-herdr/artifact-manifest.json',
    'attention_ui': E+'pr07-attention-ui.md',
    'external_attention': E+'pr10-external.md',
    'correlation': E+'pr10-correlation.md',
    'public_correction': E+'r3-public-artifact-review/milestone.md',
    'public_inventory': E+'r3-public-artifact-review/scan-after.json',
    'native_prepared': E+'r3-qualification-readiness/native-proposal/native-service-campaign-proposal.json',
    'service_campaign_doc': 'plans/agent_ops/campaigns/windows-user-service.md',
}
assert all((ROOT/p).is_file() for p in catalog.values())

# These are scope descriptions, not status promotions or a replacement plan.
ac_scope = {
    'AC-01': ('Current fixed inventory is intact and every checked ledger path exists; all 71 selected joint identities resolve to passing XML.', ['joint','joint_scope'], 'Task-by-task implementation/reuse closure is still required. Do not infer it from file/test counts; this audit does not claim all59 task obligations accepted.'),
    'AC-02': ('Installed mixed-channel/idle/isolation contracts coexist with optional OBS/attention; canonical facts remain separate.', ['joint','external_attention','correlation'], 'Combined final acceptance still depends on the declared real-provider/client/service gates; no new product defect identified here.'),
    'AC-03': ('Two MCP actors plus one runtime are proved through actual canonical MCP/HTTP/SQLite components with synthetic native I/O.', ['joint'], 'Two actual client executables participating end-to-end are not proved by these fixtures or by config parsing. Retain the explicitly authorized real-client campaign gate.'),
    'AC-04': ('Existing VERIFIED scope is supported by real browser/backend authorized actions and canonical lifecycle/ownership checks.', ['attention_ui','external_attention','correlation'], 'No additional package/inventory gap found for this criterion. Do not broaden it into a real-provider M1 claim.'),
    'AC-05': ('Recovery retains identity and one effect in the39 named current installed cases; bootstrap/renewal receipts preserve uncertainty.', ['recovery_scope','bootstrap','renewal'], 'Current selection is not every new path or real network/process failure. Retain the named unrun recovery scopes; no broad rerun requested by this audit.'),
    'AC-06': ('OBS isolation and six idle scheduler cases preserve native reservations, TTL, eligibility, ordering and authority.', ['joint','idle_scope','external_attention'], 'Link these exact scopes to the criterion/invariants; no inference of provider completion or global full-plan acceptance.'),
    'AC-07': ('Current Nexus/Connector/Core payloads match source and installed CI artifacts; corrected pins and MCP1.30 declared solve are retained.', ['current_dependencies','current_package','ci_installed','application_boundaries','core_import_scope'], 'The old DX04 browser MCP1.29.1 environment is not a valid dependency solve. Current solve is sufficient for packaging; Core audit limitations remain explicit, without inventing a new product boundary.'),
    'AC-08': ('Public package includes167 SQL migrations,7 UI files and required resources; docs/CLI milestones and current service proposal links exist.', ['current_package','guide','bootstrap','renewal','service_campaign_doc'], 'Parent must publish the already prepared service-campaign link update. Complete criterion-level documentation/schema/help trace mapping; no new application behavior requested.'),
    'AC-09': ('Closed milestones explicitly identify synthetic peers, fixture credentials, failed attempts and unrun real campaigns.', ['joint_scope','guide','native_prepared'], 'Retain these limitations in final closure, especially historical invalid dependency solve and unqualified client/service/provider scopes. Avoid fixture-to-real-campaign promotion.'),
    'AC-10': ('Eight existing protection functions have passing retained XML; bcf0e8aa removes two public literals and retains structural outcomes/provenance.', ['bootstrap_tests','participant_tests','observer_tests','public_correction','public_inventory'], 'Historical UAT credential validity/revocation is unknown; previous Git commits were intentionally not rewritten, and visual/binary content is outside the pattern scan. AC10 cannot be closed by this read-only review.'),
    'AC-11': ('Installed terminal/bootstrap/work/recovery contracts are exercised with synthetic native peers.', ['bootstrap','renewal','recovery_scope'], 'The required real harness cycle with work, authorized decision and result on local Server and Connector remains an explicitly authorized campaign; service/session ready is insufficient.'),
    'AC-12': ('No package or public-inventory inconsistency found. Existing service/root authority contracts are retained separately from these joint tests.', ['native_prepared','bootstrap'], 'Physical service concurrency/supervisor qualification remains in its declared real service scope; this audit did not rerun or infer it.'),
    'AC-13': ('The24-action Windows temporary-service proposal pins current binaries, isolated homes and explicit cleanup and remains prepared only.', ['native_prepared','service_campaign_doc'], 'Actual registration/login/stop/crash recovery/removal/context/credential qualification requires explicit campaigns. The24-action no-login/no-crash proposal does not replace the full criterion.'),
    'AC-14': ('Current selected recovery and explicit credential-rotation reconnect contracts preserve ownership and uncertainty.', ['recovery_scope','renewal'], 'Real suspension/service/network/provider campaigns remain separate. TLS/two-host proof is required only for scopes declared supported/qualified, not invented as a universal new mandate.'),
    'AC-15': ('Existing diagnostic/control implementation evidence is retained; package includes the public CLI entry points and help.', ['current_package','native_prepared'], 'Actual native lifecycle/control campaign remains unrun; this audit adds no repeated regression run or global passivity claim.'),
    'AC-16': ('Persistent default identity and preset/reconnect contracts are documented and tested in the published milestones.', ['bootstrap','renewal'], 'Effective native harness limits/instructions and real-use acceptance still require the declared actual harness campaign; no new global identity/admin authority is implied.'),
    'AC-17': ('Completed reconnect after explicit rotation preserves original bootstrap, binding, configuration and Finish; browser guide is additive.', ['renewal','guide'], 'Record exact installed/browser scope; broader real-client/provider/service acceptance remains unclaimed. No further product omission demonstrated in this inventory audit.'),
}
criteria = []
for item in prior['criteria']:
    key = item['id']
    if key not in ac_scope:
        continue
    assert item['requirement_exact'] in plan
    proven, refs, missing = ac_scope[key]
    criteria.append({'id': key, 'requirement_exact': item['requirement_exact'], 'ledger_status_at_5545dbde': ledger['completion_criteria'][key]['status'], 'proven_scope_in_this_review': proven, 'evidence': [catalog[x] for x in refs], 'remaining_or_limit': missing, 'status_changed': False})
assert len(criteria) == 17

inv_links = {
    'INV-01': ['joint','bootstrap','renewal'],
    'INV-03': ['core_import_scope','application_boundaries','current_dependencies'],
    'INV-05': ['idle_scope','external_attention','correlation'],
    'INV-06': ['idle_scope','external_attention','recovery_scope'],
    'INV-07': ['attention_ui','external_attention','correlation'],
    'INV-08': ['external_attention','correlation'],
    'INV-09': ['joint'],
    'INV-10': ['recovery_scope','bootstrap','renewal'],
    'INV-11': ['bootstrap_tests','participant_tests','observer_tests','public_correction'],
    'INV-12': ['joint_scope','guide','native_prepared'],
    'INV-13': ['external_attention','correlation'],
    'INV-24': ['native_prepared','service_campaign_doc'],
    'INV-26': ['bootstrap','renewal'],
    'INV-28': ['joint_scope','native_prepared'],
}
invariants = []
for key, text in re.findall(r'^\| (INV-\d+) \| (.*?) \|$', plan, re.M):
    stored = ledger['invariants'][key]
    invariants.append({'id': key, 'requirement_exact': text, 'ledger_status_at_5545dbde': stored['status'], 'existing_evidence_count': len(stored.get('evidence',[])), 'existing_subscopes': stored.get('subscopes',{}), 'additional_scoped_references_reviewed': [catalog[x] for x in inv_links.get(key,[])], 'disposition': 'Cross-reference only: follow each cited scope/limitation; no invariant promotion.' if key in inv_links else 'No new closure claim. Existing ledger evidence or explicit campaign gap retained; zero references is not proof of absent implementation.'})
assert len(invariants) == 28

findings = [
    {'id': 'TRACE-01', 'priority': 'remaining_acceptance_limit', 'requirements': ['AC-10','INV-11'], 'finding': 'Public snapshot correction is complete in bcf0e8aa, but historical UAT credential validity/revocation and prior Git history are outside the reviewed closure.', 'minimum_action': 'Retain NOT_VERIFIED with exact residual scope; use protection-tests.json and public-review provenance as scoped evidence. Any credential-owner/history action requires separate authorized handling; this audit neither authenticates nor expands to history rewrite.', 'evidence': [catalog['public_correction'],catalog['public_inventory'],'protection-tests.json'], 'new_product_change_required': False},
    {'id': 'TRACE-02', 'priority': 'safe_traceability_completion', 'requirements': ['AC-01','AC-07','AC-08','AC-09','RG-08','RG-09','INV-03','INV-05','INV-06','INV-09','INV-11'], 'finding': 'The5545 ledger underlinks current evidence: RG09 cites only Herdr, while mixed/sessions/guide drivers retain newer isolation; INV03 and INV09 have no direct references despite bounded Core/joint proofs. Missing links are not missing implementation.', 'minimum_action': 'Root may attach the finite evidence-to-scope links from this report, keeping unqualified portions and all global statuses unchanged until their actual criteria are met. No repeated test run needed for this association.', 'evidence': ['traceability.json','verification.json','protection-tests.json'], 'new_product_change_required': False},
    {'id': 'TRACE-03', 'priority': 'pending_parent_document_publish', 'requirements': ['AC-08','AC-09','INV-24'], 'finding': 'The old Windows campaign document referred only to historical PR02 artifacts. Parent already prepared the correct link to the current proposal; it is not part of the5545 baseline.', 'minimum_action': 'Publish only the prepared document update with its current proposal hash; preserve NOT_AUTHORIZED_NOT_RUN and historical snapshot.', 'evidence': [catalog['service_campaign_doc'],catalog['native_prepared'],'supplemental-checks.json'], 'new_product_change_required': False},
    {'id': 'TRACE-04', 'priority': 'explicit_unrun_campaigns', 'requirements': ['AC-02','AC-03','AC-11','AC-12','AC-13','AC-14','AC-15','AC-16','AC-17','RG-07'], 'finding': 'No new implementation defect was established by the public-inventory review. RG07 is owned by the parallel compatibility campaign; actual client/provider/native-service and joint acceptance scopes remain distinct from fixtures.', 'minimum_action': 'Consume the separately retained RG07 result when closed. Run only specifically authorized real campaigns against pinned artifacts and isolated homes, with individual scope/cleanup evidence. Do not create universal TLS/two-host or extra platform requirements.', 'evidence': [catalog['joint_scope'],catalog['native_prepared']], 'new_product_change_required': False},
]

isolation = [
    {'scope': 'RG01/RG02/RG11 mixed', 'evidence': [catalog['mixed_isolation'],catalog['mixed_installed']], 'proven': 'Driver clears named application/provider variables before imports, sets disposable USERPROFILE/APPDATA/LOCALAPPDATA, uses isolated cwd/pytest basetemp and checks loaded product modules in the qualified venv. Existing fixtures supply temporary project/home and synthetic native authentication.', 'limit': 'This is the selected canonical fixture campaign, not actual MCP client/provider/service qualification or a universal syscall sandbox.'},
    {'scope': 'RG04 sessions', 'evidence': [catalog['sessions_isolation'],catalog['sessions_invocation']], 'proven': 'Runner constructs OS-only environment allowlist, disposable profile/appdata/temp directories, independent cwd and Python-I; installed runner verifies wheel payloads before execution.', 'limit': 'No personal account/config state comparison is implied outside selected fixture effects. Native peer/service authority remains synthetic.'},
    {'scope': 'RG03 idle / selected RG05 recovery', 'evidence': [catalog['idle_scope'],catalog['idle_runner'],catalog['recovery_scope'],catalog['recovery_runner']], 'proven': 'Reports identify synthetic native peers and fixture credentials; selected fixtures use temporary SQLite/homes. Runners retain redacted output and own temp/cache directories.', 'limit': 'These wrappers inherit ambient environment instead of recording the RG04-style full allowlist. Do not describe all71 cases as proving identical hermetic OS/profile isolation. This is a limit of retained isolation evidence, not proof of a personal-config mutation.'},
    {'scope': 'DX04 browser', 'evidence': [catalog['guide'],catalog['guide_server_driver']], 'proven': 'Actual installed backend/browser campaign retains isolated homes, table before/after observations and canonical cleanup.', 'limit': 'Historical MCP1.29.1 environment is not dependency-solve proof; current CI solve is separately pinned. UI observations remain historical.'},
]

rg = []
for key in ('RG-08','RG-09'):
    exact = re.search(r'^\| '+key+r' \| (.*?) \|',plan,re.M).group(1)
    rg.append({'id': key,'requirement_exact': exact,'ledger_status_at_5545dbde': ledger['scenarios'][key]['status'],
               'proven_scope': 'Current wheel completeness and bytes verified for all three packages; UI, SQL, Core schemas and resources present; installed-only proof and current dependency solve retained.' if key=='RG-08' else 'Selected closed campaigns retain disposable homes/workspaces and synthetic native/account boundaries, with the exact differences detailed in isolation_scopes.',
               'remaining': 'No package-file or pin defect found. Link current artifact proof; do not carry historical dependency mismatch as an unresolved current pin defect.' if key=='RG-08' else 'Map each campaign scope to its evidence; current global row is underlinked. Future real campaigns must separately retain isolated profiles/cleanup and no-personal-config proof; the stronger launcher proof must not be generalized to all prior wrappers.',
               'evidence': [catalog[x] for x in (['current_package','current_dependencies','ci_installed'] if key=='RG-08' else ['mixed_isolation','sessions_invocation','guide_server_driver','herdr'])], 'status_changed': False})

report = {
    'format': 'r3.final-public-traceability-review', 'version': 1,
    'baseline': verification['baseline'],
    'followup_separate_from_baseline': supplement['public_review_followup'],
    'scope': 'Finite read-only audit of literal ACs, RG08/RG09 and INV references, public file inventory, current pins/resources and existing protection assertions/results. No product, ledger, closed evidence or global status changed.',
    'actions_not_executed': ['tests','builds','product imports','provider/native service/client campaigns','credentials/accounts/configuration access','Git-history rewrite','commit/push'],
    'verified': {'manifest_entry_checks_including_nested_overlap': 1384,'manifest_hash_size_path_errors': 0,'local_literal_ledger_reference_paths': 724,'explicit_evidence_list_paths': 428,'missing_ledger_paths': 0,'joint_unique_passed_identities': 71,'package_payload_files': {'nexus':690,'connector':123,'core':165},'package_mismatches':0,'source_resources_missing_from_wheel':0,'existing_protection_functions':8},
    'findings': findings, 'completion_criteria': criteria, 'regression_requirements': rg,
    'invariants': invariants, 'isolation_scopes': isolation,
    'herdr_inventory_resolution': supplement['herdr_supplemental_inventory'],
    'literal_closure_recommendations_for_parent': {
        'RG-08': 'Sufficient for the current exact Windows package set: all690/123/165 source resources are in the wheels, installed payload equality is retained, and UI/schema/migration resources are present without sibling application imports. No concrete literal package gap remains.',
        'AC-07': 'Sufficient for the current snapshot with the current declared dependency solve/pipcheck, exact pins/payloads, reviewed application boundaries and the separately closing RG06 import131 audit. Actual provider/client/service campaigns are not prerequisites of this literal boundary/dependency criterion.',
        'AC-09': 'Sufficient as an honest snapshot declaration when this finite matrix, named NOT_RUN inventory and explicit synthetic-vs-real limits are retained. Executing named unrun tests is not required by this criterion.',
        'authority': 'Recommendations only; parent owns the final ledger decision. This subagent did not mutate or promote any status.',
    },
    'protection_test_detail': 'protection-tests.json',
    'evidence_catalog': catalog,
    'conclusion': 'No additional product defect or missing package resource identified in this bounded audit. Current public inventory/payload proofs are sufficient for their stated scope. Remaining work is precise traceability, the already prepared document update, parallel compatibility qualification and explicitly unqualified real campaigns; AC10 retains its historical credential limit. No automatic status promotion.',
}
(OUT/'traceability.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

text = '''# Revisão finita de rastreabilidade R3

Base: Nexus `5545dbde`, Connector `fb3fff47`, Core `5d317843`. Plano R3 SHA-256 `20d0fafdedc793b97a277f5d41355d7d597ff724a77687394215eea3113ba996`; conjuntos59/132/28/17 preservados. Seguimento público `bcf0e8aa` tratado separadamente. Somente leitura; nenhuma suíte, build, campanha real, credencial ou serviço foi executado/acessado, e nenhum status foi promovido.

Não encontrei defeito adicional de produto ou recurso ausente nos pacotes. Conferi1.384 entradas de manifests, inclusive sobreposições entre manifests aninhados: zero divergência de hash/tamanho/caminho. As724 referências locais literais examinadas e428 caminhos das listas `evidence` existem. As71 identidades únicas do milestone conjunto apontam a casos aprovados nos XMLs indicados; reruns não foram somados.

| Pacote | Arquivos fonte/wheel | Recursos conferidos |
|---|---:|---|
| Nexus0.3.3 | 690 | 513 Python,167 migrações SQL,7 arquivos UI,3 outros recursos; bytes iguais também à instalação CI |
| Connector0.0.12 | 123 | 122 Python e `py.typed`; pin a8cf1810 atual |
| Core0.0.14 | 165 | 131 Python,31 schemas JSON,2 recursos JS e `py.typed`; pin5721e462 atual |

Nenhum arquivo de recurso fonte ficou fora dos wheels. O solve atual com MCP1.30/pip check corrige o pin antigo e a insuficiência do ambiente histórico de browser MCP1.29.1; isso não transforma o browser histórico em prova de solve.

## Mínimo restante

1. **Rastreabilidade por escopo:** RG09 ainda só cita Herdr no baseline. Ligar os drivers/relatórios atuais de mixed, sessões e browser, e os vínculos específicos INV03/05/06/09/11 fornecidos no JSON. Contagem e ausência de link não provam ausência de implementação; nenhuma promoção global é sugerida.
2. **AC10/INV11:** a correção bcf0e8aa removeu dois literais do snapshot público e preservou os resultados. Os oito testes de proteção abaixo já têm aprovações retidas. A validade/revogação da chave UAT histórica segue desconhecida; o histórico Git e o conteúdo visual/binário não foram certificados. Manter esse limite; não reescrever histórico nem usar a chave como parte desta tarefa.
3. **Documento de campanha:** publicar a atualização já preparada pelo root em `plans/agent_ops/campaigns/windows-user-service.md`, que liga a proposta vigente SHA `fbf8644cf836886bc7bac596211a783d6090e79077c643b1d2a627c87a3a37e3`. Seus24 comandos continuam não autorizados/não executados.
4. **Aceites distintos:** consumir RG07 quando a campanha paralela fechar. Dois clientes reais, harness/provedor real e serviço nativo/login/crash/contexto continuam dependências de campanhas explícitas. TLS/dois hosts só se aplicam ao escopo que for declarado qualificado; não constituem requisito universal novo. Nenhuma repetição ampla de testes é indicada por esta auditoria.

## Isolamento: o que a evidência permite afirmar

Mixed limpa variáveis de aplicação/provedor e fixa profile/appdata/cwd/basetemp temporários antes dos imports; valida origem dos módulos. RG04 retém allowlist do SO e todos os diretórios descartáveis, com Python-I e verificação instalada. São evidências suficientes para essas campanhas sintéticas selecionadas.

Os wrappers RG03/RG05 retêm temp/cache próprios, redigem saída e usam fixtures temporárias, mas herdam o ambiente em vez de reter a mesma allowlist completa de RG04. Não generalizar a prova mais forte para todos71 casos. Isso é limite da prova de isolamento, não demonstração de alteração pessoal. Campanhas reais futuras precisam de seus próprios limites e fechamento.

## Inventário Herdr resolvido

`collect_artifacts.py` é o driver de fechamento/verificação citado pelo milestone. `initial-manifest.json` é o manifesto histórico de316 testes/11 relatórios, preservado pelo collector. Ambos estão fora das142 entradas do manifesto principal por função de proveniência, e ambos já constam com hashes exatos no inventário público `r3-public-artifact-review/scan-after.json`. Não há artefato de runtime perdido nem necessidade de reescrever o manifesto fechado; `supplemental-checks.json` registra a associação.

## Proteções já aprovadas, sem rerun

| Proteção inspecionada | Fonte | Resultado retido suficiente |
|---|---|---|
| Material único fora de resultado/checkpoint/export; recibo com campo secreto recusado; material somente TTY separado do stdout | `tests/execution_r4/test_remote_terminal_setup.py:209,263,308` | `pr03-remote-bootstrap/candidate-v1/nexus/installed.xml`:3 casos |
| Fallback de prompt ecoado interrompido; erro HTTP malformado sanitizado; redirect HTTP real sem encaminhar Bearer | `tests/execution_r4/test_participant_init.py:228,268,279` | `pr04-participant-removal-installed.xml`:4 casos |
| Erro do processo/launcher sem segredo na saída | `tests/execution_r4/test_participant_launch.py:189` | `pr04-participant-removal-installed.xml`:1 caso |
| Origem inválida sanitizada na construção do cliente | `tests/test_observation_client.py:209` | `pr09-herdr/installed/qualified-v2/pr09-observation-installed-v2-initial.xml`:14 casos parametrizados |

São8 funções/22 identidades selecionadas, não uma nova execução nem uma certificação universal contra vazamento. `protection-tests.json` contém assertions reais, hashes de função/relatório e todas as aprovações sobrepostas, sem somá-las; parâmetros são representados por digest de identidade. AC04 mantém a avaliação existente apoiada por ações autorizadas no browser/backend; nenhum requisito de provedor real foi acrescentado a esse critério.

Detalhes: `traceability.json` inclui os17 ACs e28 invariantes literais, RG08/RG09, limites e referências. `verification.json`, `payload-verification.json` e `supplemental-checks.json` retêm os resultados verificáveis. Esta revisão não substitui o aceite global R3.
'''
# Adjust prose spacing without touching commit IDs, hashes or file names.
for before, after in {
    'conjuntos59/132/28/17': 'conjuntos 59/132/28/17',
    'Conferi1.384': 'Conferi 1.384', 'As724': 'As 724', 'e428': 'e 428', 'As71': 'As 71',
    'Nexus0.3.3': 'Nexus 0.3.3', 'Connector0.0.12': 'Connector 0.0.12', 'Core0.0.14': 'Core 0.0.14',
    'Python,167': 'Python, 167', 'SQL,7': 'SQL, 7', 'UI,3': 'UI, 3', 'Python,31': 'Python, 31', 'JSON,2': 'JSON, 2',
    'pin5721e462': 'pin 5721e462', 'MCP1.30': 'MCP 1.30', 'MCP1.29.1': 'MCP 1.29.1',
    'Seus24': 'Seus 24', 'todos71': 'todos 71', 'de316': 'de 316', 'das142': 'das 142',
    'São8': 'São 8', 'funções/22': 'funções / 22', 'os17': 'os 17', 'e28': 'e 28',
}.items():
    text = text.replace(before, after)
text += '\nRecomendação literal ao root: a prova atual é suficiente para RG-08. AC-07 também é atendido pelo solve/pins/fronteiras atuais e pelo RG-06 em fechamento separado; não depende de campanhas de provedor. AC-09 pode ser concluído como declaração honesta do snapshot ao reter o inventário nomeado NOT_RUN e seus limites, sem exigir que esses testes sejam executados. A decisão e qualquer atualização do ledger pertencem ao root.\n'
(OUT/'traceability.md').write_text(text,encoding='utf-8')

public = ['traceability.json','traceability.md','verification.json','protection-tests.json','payload-verification.json','supplemental-checks.json','verify_traceability.py','protection_and_payload.py','supplemental_checks.py','build_report.py']
manifest = {'format':'r3.final-traceability.allowlist','version':1,'baseline':verification['baseline'],'files':{p:{'bytes':(OUT/p).stat().st_size,'sha256':sha((OUT/p).read_bytes())} for p in public},'excluded':['inspect_manifest_shapes.py (inspection helper only)','all private homes, databases, vaults, runtime state and credential values'],'tests_executed':False,'checkout_edited':False,'global_status_promoted':False}
(OUT/'artifact-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'directory':str(OUT),'public_files':len(public),'manifest_sha256':sha((OUT/'artifact-manifest.json').read_bytes()),'report_sha256':sha((OUT/'traceability.json').read_bytes()),'criteria':len(criteria),'invariants':len(invariants),'new_tests_executed':0},indent=2))
