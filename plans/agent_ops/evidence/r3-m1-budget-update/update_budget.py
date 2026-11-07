from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import shutil

repo = Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
old = repo / 'plans/agent_ops/evidence/r3-campaign-proposals/m1-codex-campaign-proposal.json'
target = repo / 'plans/agent_ops/evidence/r3-m1-budget-update'
assert not target.exists()
target.mkdir()
prefix = target.relative_to(repo).as_posix()
proposal = json.loads(old.read_text(encoding='utf-8'))
assert proposal['revision'] == 3
proposal['revision'] = 4
proposal['status'] = 'BUDGET_CLARIFIED_PREPARATION_AND_EXECUTION_AUTHORIZATION_PENDING'
proposal['authorization']['received'] = ('Account already authenticated in Codex CLI. User subsequently said '
    '"pode exceder o limite em 500k tokens": interpreted as 500000 additional tokens over the original '
    '200000, for a 700000 total tolerance. This budget clarification does not authorize separate service '
    'installation or native credential use/inference previously reserved for explicit execution approval.')
proposal['authorization'].pop('clarification_pending')
proposal['authorization']['budget_clarification'] = dict(status='RESOLVED', original_tokens=200000,
    additional_tolerance_tokens=500000, total_tolerance_tokens=700000,
    interpretation='Additional allowance, not a replacement 500000 total.')
accounting = proposal['token_accounting']
accounting['original_requested_total'] = 200000
accounting['user_requested_total'] = 700000
accounting['additional_tolerance_tokens'] = 500000
accounting['operational_limit_accepted'] = True
accounting['limitation'] = accounting.pop('blocker').replace('a strict 200000 ceiling', 'an atomic hard ceiling')
policy = accounting.pop('operational_variant_not_yet_authorized')
policy['meaning'] = ('Stop new admissions and request preventive interruption at 100000 reported aggregate '
    'tokens, retaining the conservative threshold. The user allows up to 500000 overshoot over the '
    'original 200000 budget, hence 700000 total tolerance. Reporting and interruption remain asynchronous; '
    'this is operational monitoring, not an atomic native hard cap. Missing/incomplete accounting stops '
    'admission. No extra turns are admitted to consume the allowance. Execution authorization is separate.')
accounting['operational_policy'] = policy
proposal['blocking_preconditions_before_execution_request'] = [
    item for item in proposal['blocking_preconditions_before_execution_request']
    if not item.startswith('Clarify the requested token ceiling:')]
proposal['supersedes_proposal_sha256'] = hashlib.sha256(old.read_bytes()).hexdigest()
proposal['supersedes_proposal_path'] = old.relative_to(repo).as_posix()
proposal['revision_note'] = ('User budget clarification only. Original proposal v3 and its manifests remain '
    'unchanged. Total tolerance700000; preventive stop100000; finite maximum6 admissions unchanged. '
    'Preparation gaps and execution approval remain explicit; no new acceptance or provider execution.')
new_proposal = target / 'm1-codex-campaign-proposal-v4.json'
new_proposal.write_text(json.dumps(proposal, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
note = '''
## 2026-11-07 — tolerância de orçamento M1

O usuário informou: “pode exceder o limite em 500k tokens”. A interpretação
registrada é 500 mil adicionais aos 200 mil originais, total de 700 mil tokens.
Mantém-se a interrupção preventiva aos 100 mil tokens reportados, no máximo
seis admissões seriais incluindo testes de setup, e recusa de novas admissões
quando a contabilidade estiver incompleta. A margem não é uma meta de consumo.
O fluxo nativo continua sem corte atômico de tokens; a política é operacional.

A proposta v4 substitui a v3 como referência atual; os artefatos anteriores
permanecem imutáveis. A dúvida de orçamento foi resolvida. Preparação do coletor
de uso/recuperação e autorização de execução real/serviços permanecem explícitas.
Nenhuma credencial real, inferência ou tarefa do SO foi usada nesta revisão;
nenhum status de tarefa/cenário/aceite foi promovido.
Evidência: `plans/agent_ops/evidence/r3-m1-budget-update/m1-codex-campaign-proposal-v4.json`.
'''
(target / 'milestone.md').write_text(note.lstrip(), encoding='utf-8')
shutil.copy2(__file__, target / 'update_budget.py')
ledger_path = repo / 'plans/agent_ops/ledger.json'
ledger = json.loads(ledger_path.read_text(encoding='utf-8'))
campaign = ledger['campaigns']['m1_codex_real']
campaign.update(status='BUDGET_CLARIFIED_PREPARATION_AND_AUTHORIZATION_PENDING',
    original_token_limit=200000, additional_token_tolerance=500000, total_token_limit=700000,
    preventive_interrupt_tokens=100000,
    budget_limit='User permits500000 additional tokens over200000. Operational tolerance700000; preventive interruption100000; native hard cap unavailable.',
    proposal=prefix + '/m1-codex-campaign-proposal-v4.json')
ledger['updated_at'] = datetime.now(timezone.utc).isoformat()
ledger['history'].append(dict(date='2026-11-07', milestone='M1 budget tolerance clarified', status='PREPARED',
    summary='User allows500k additional tokens:700k total tolerance; preventive100k retained. Preparation and execution authorization remain separate; no provider use.',
    evidence=[prefix + '/milestone.md']))
ledger_path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
for name in ('LEDGER_CODEX_NEXUS_INTEGRACAO_ATENCAO_ONBOARDING.md', 'plans/agent_ops/implementation-report.md'):
    with (repo / name).open('a', encoding='utf-8') as stream:
        stream.write(note)
with (repo / '.gitattributes').open('a', encoding='utf-8') as stream:
    stream.write(prefix + '/** -text -whitespace\n')
files = {p.relative_to(target).as_posix(): dict(sha256=hashlib.sha256(p.read_bytes()).hexdigest(), bytes=p.stat().st_size)
         for p in sorted(target.rglob('*')) if p.is_file()}
(target / 'artifact-manifest.json').write_text(json.dumps(dict(files=files,
    previous_proposal_sha256=proposal['supersedes_proposal_sha256']), indent=2) + '\n', encoding='utf-8')
assert not any(proposal['authorization'][key] for key in ('inference_authorized', 'credential_use_authorized', 'service_install_authorized'))
assert policy['interrupt_threshold'] == policy['new_admission_stop_threshold'] == 100000
assert proposal['finite_work']['maximum_productive_admissions'] == 6
print(json.dumps(dict(revision=4, original=200000, additional=500000, total=700000, preventive=100000)))
