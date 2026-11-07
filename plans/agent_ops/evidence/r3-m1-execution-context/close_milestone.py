from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import shutil

repo = Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
source = Path('C:/Users/jpamb/AppData/Local/Temp/m1-context-preparation-v0u6i9vu')
target = repo / 'plans/agent_ops/evidence/r3-m1-execution-context'
assert not target.exists()
target.mkdir()
for name in ('context.json', 'discovery.json', 'proposed-commands.json', 'prepare_context.py', 'prepare_discovery.py', 'prepare_commands.py'):
    shutil.copy2(source / name, target / name)
context = json.loads((target / 'context.json').read_text())
discovery = json.loads((target / 'discovery.json').read_text())
commands = json.loads((target / 'proposed-commands.json').read_text())
old = repo / 'plans/agent_ops/evidence/r3-m1-budget-update/m1-codex-campaign-proposal-v4.json'
proposal = json.loads(old.read_text(encoding='utf-8'))
prefix = target.relative_to(repo).as_posix()
proposal['revision'] = 5
for step in proposal['steps']:
    step['commands'] = [command + ' --home <operator_home>'
                        if ('--operator-profile' in command or '<NEXUS> operator login ' in command)
                        and '--home ' not in command else command for command in step['commands']]
    if step['id'] == '08-close-drain-cleanup':
        step['commands'] = [command.replace('--timeout 60', '--timeout 45') for command in step['commands']]
proposal['paths']['codex_executable'] = commands['native']
proposal['native_selection']['executable'] = commands['native']
proposal['native_selection']['candidate_ref'] = commands['candidate_ref']
proposal['native_selection']['passive_discovery_evidence'] = prefix + '/discovery.json'
proposal['native_selection']['required_binding'] = 'Review and approve this exact passively discovered installation reference, executable and project through the canonical setup; passive discovery is not launch authority.'
proposal['provider_context']['provider_home'] = commands['provider_home']
proposal['provider_context']['status'] = 'Candidate default native state path pinned from environment/default-home semantics only; no personal file contents read. Native use of existing authentication remains awaiting execution authorization.'
proposal['topology'].update(origin=commands['origin'], task_names={k:v['name'] for k,v in context['tasks'].items()},
    service_commands=prefix + '/proposed-commands.json', service_selection_args=commands['service_selection_args'])
proposal['blocking_preconditions_before_execution_request'] = [
    'Finish and review finite usage collector, response-loss driver and their campaign integration using installed synthetic event shapes before real provider execution.',
    'Explicitly authorize native use of the pinned existing provider home and the finite M1 work; its contents and login remain uninspected.',
    'Explicitly authorize the two exact M1 user tasks and eight proposed lifecycle actions, separately from the 24-action empty-service proposal. Recheck ownership/absence, empty paths and port immediately before effects.',
]
proposal['runtime_qualification_limits'] = [
    'Actual policy may not produce a qualified permission request. Do not change policy to fabricate one; retain that native-decision gate pending.',
    'Installed byte verification and pure discovery do not qualify productive M1 work, native helpers, provider login or user-service behavior.',
]
proposal['supersedes_proposal_sha256'] = hashlib.sha256(old.read_bytes()).hexdigest()
proposal['supersedes_proposal_path'] = old.relative_to(repo).as_posix()
proposal['revision_note'] = ('Pinned exact M1 service targets/origin/argv and candidate provider path without reading personal files. '
    'Verified all three installed wheel payloads. Preserved the official package and prepared an isolated complete copy '
    'with additional codex.exe name required by passive local PATH discovery; executable bytes unchanged. '
    'Collector/driver integration still pending; no native process, service mutation, provider use or acceptance promotion.')
(target / 'm1-codex-campaign-proposal-v5.json').write_text(json.dumps(proposal, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
note = '''
## 2026-11-07 — contexto concreto da campanha M1

Conferidos os três pacotes instalados: Nexus 691 arquivos, Connector 124 e Core
166, todos idênticos às wheels fixadas. Os dois nomes de tarefas M1 foram
derivados pelos componentes instalados e consultados como ausentes; nenhum
serviço foi registrado. Homes de campanha ainda ausentes; porta 64507 livre no
instante da preparação, sujeita a nova conferência antes de qualquer efeito.

O executável oficial extraído tinha nome codex-x86_64-pc-windows-msvc.exe, que
não é encontrado pela descoberta PATH local de codex.exe. Uma cópia completa
isolada da distribuição recebeu também esse nome esperado, com os mesmos
bytes; a descoberta passiva confirmou o candidato selecionado. Nenhum binário
foi executado nem a instalação pessoal alterada. Os 48 arquivos da cópia
foram conferidos; não se infere qualificação de helpers por mera igualdade.

O candidato de provider home C:/Users/jpamb/.codex deriva do ambiente/default,
sem abrir arquivos pessoais. A proposta v5 fixa oito ações de lifecycle M1
para seus dois recursos, distintos das 24 ações vazias anteriormente propostas.
Mantém 700 mil de tolerância total e preventiva de 100 mil. Coletor/driver e
integração de campanha continuam em preparação; uso nativo da conta e ações
de serviço seguem sem autorização. Nenhum status de aceite foi promovido.
Evidência: `plans/agent_ops/evidence/r3-m1-execution-context/m1-codex-campaign-proposal-v5.json`.
'''
(target / 'milestone.md').write_text(note.lstrip(), encoding='utf-8')
shutil.copy2(__file__, target / 'close_milestone.py')
ledger_path = repo / 'plans/agent_ops/ledger.json'
ledger = json.loads(ledger_path.read_text(encoding='utf-8'))
ledger['campaigns']['m1_codex_real'].update(proposal=prefix + '/m1-codex-campaign-proposal-v5.json',
    context_preparation=prefix + '/context.json', native_discovery=prefix + '/discovery.json',
    build_qualification='Exact official0.157.0 bytes copied into an isolated complete package with additional codex.exe discovery name; passive candidate selected. Native behavior remains unexecuted.')
ledger['updated_at'] = datetime.now(timezone.utc).isoformat()
ledger['history'].append(dict(date='2026-11-07', milestone='Exact M1 execution context prepared', status='PREPARED',
    summary='Three installed payloads verified; exact tasks absent, scratch paths absent, candidate provider path and lifecycle argv pinned; passive discovery fixed with isolated byte-identical codex.exe copy. No provider or service effects.',
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
    scope='Preparation only; copied executable/package bytes are retained in Temp and never committed'), indent=2) + '\n')
print(json.dumps(dict(revision=5, public_payloads=len(files), native_executions=0, service_mutations=0)))
