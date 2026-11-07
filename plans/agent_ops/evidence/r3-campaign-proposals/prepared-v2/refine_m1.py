"""Refine only a new proposal version; no campaign fixture or runtime creation."""
from pathlib import Path
from copy import deepcopy
import hashlib
import json

ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT / 'public'
OLD = Path('C:/Users/jpamb/AppData/Local/Temp/m1-codex-campaign-proposal-ynzvp8yx/public')
original = OLD / 'm1-codex-campaign-proposal.json'
value = deepcopy(json.loads(original.read_bytes()))
value['revision'] = 2
value['supersedes_proposal_sha256'] = hashlib.sha256(original.read_bytes()).hexdigest()
value['prior_public_manifest_sha256'] = hashlib.sha256((OLD / 'artifact-manifest.json').read_bytes()).hexdigest()
value['authorization']['clarification_pending'] = 'Root asked whether the 200000 token limit is rigid or operational with preventive interruption at 100000 reported tokens. No response or execution authorization has been received.'
campaign = ROOT / 'm1-campaign'
value['paths'].update({key: str(campaign / relative) for key, relative in {
    'campaign_root': '.', 'server_home': 'nexus-home', 'operator_home': 'operator-home',
    'connector_state': 'connector-state', 'local_project': 'local-project',
    'remote_project': 'connector-project', 'private_evidence': 'private', 'public_evidence': 'public',
    'local_deliverables': 'deliverables/local', 'remote_deliverables': 'deliverables/connector',
}.items()})
for label, component, filename, digest in (
    ('nexus', 'nexus-wheel-v1', 'okto_nexus-0.3.3-py3-none-any.whl', 'cd1653dbdb48031e6c04771889ecc3efa5de965973dfe29026436fe263b478ad'),
    ('connector', 'nexus-source-v1/vendor/ci', 'okto_nexus_connector-0.0.12-py3-none-any.whl', '73f1a3ba6daf1a4db6f98a9eaf7badaed0d32b151a30b4c0c6a0cf66c2eae1b5'),
    ('core', 'core-v2-wheels', 'okto_nexus_connector_core-0.0.14-py3-none-any.whl', '1407014ea12f7e6f04ac70b9da8dbf8ebd9a57d8021bb5e74437bc22bd274f7a'),
):
    value['package_pins'][label] = dict(status='CANDIDATE_HASH_PINNED_QUALIFICATION_PENDING',
        wheel=str(Path('C:/Users/jpamb/AppData/Local/Temp/r3-cooperative-drain-09ucmgsr') / component / filename),
        wheel_sha256=digest, installed_import_sha256=None, python_path=None)
work = value['finite_work']
work['request'] = (
    'Read only <project>/numbers.csv. Calculate its data row count, sum and SHA-256. '
    'Write exactly one JSON object with keys row_count, sum and input_sha256 to '
    '<lane_deliverables>/report.json. The deliverables directory is a precreated disposable '
    'sibling outside this project writable root but inside the campaign Temp root. '
    'Do not change permissions, sandbox, writable roots or global policy to perform this task. '
    'If the actual native policy requires a command permission, request it through the native '
    'mechanism and wait for the human decision. Do not read or write other paths, use the network, '
    'install tools, spawn subagents or retry a denied command with another method.')
work['delivery'] = {
    'local_output': str(campaign / 'deliverables/local/report.json'),
    'connector_output': str(campaign / 'deliverables/connector/report.json'),
    'setup': 'After authorization only, controller creates empty lane deliverables directories; no report exists before the productive request.',
    'expected_shape': {'row_count': 4, 'sum': 10, 'input_sha256': hashlib.sha256(work['fixture']['numbers.csv'].encode()).hexdigest()},
    'scope': 'Each source is only its selected project/numbers.csv and each output is only its lane report.json. No overwrite of any pre-existing file.',
    'writable_root_check': 'Use reported effective native policy to verify the sibling is outside the project writable roots. This proposal does not modify sandbox or widen allowed paths. If effective roots already include it, do not pretend a native approval occurred.',
    'native_request_review': 'A future approval covers only the actual exact command and these source/output paths; reject any additional command/path, persistent prefix, external network use or policy relaxation.',
    'non_guarantee': 'The sibling output can provoke a legitimate native request under a restricting policy, but is not guaranteed to do so. If no qualified request appears, the useful result may pass while the native-decision M1 case remains pending.',
}
work['native_decision'] = (
    'Review one genuine item/commandExecution/requestApproval per topology. Approve only the '
    'actual exact command that reads the lane numbers.csv and writes its one report.json. '
    'No broad prefix or persistent approval; no policy/sandbox modification. If policy admits '
    'the write without a request, record native-decision evidence as pending, not inferred. '
    'If denied, do not bypass the decision through another tool or output path.')
work['continuation'] = 'Using only the existing canonical result, state the reported sum once. Do not run another command or write another file.'
value['provider_context']['decision_gate'] = (
    'The sibling deliverable remains outside project writable roots under the actual reviewed '
    'policy; only a genuine qualified commandExecution/requestApproval is accepted. No request '
    'means this gate remains pending. Never change a personal/global sandbox policy merely to force a request.')
for row in value['steps']:
    if row['id'] in ('03-local-work-decision-result', '06-connector-work-decision-loss-recovery'):
        row['required_evidence'] += (
            ' Confirm report.json exists only at the exact lane destination and its parsed '
            'row_count/sum/input_sha256 match the fixture. Preserve the actual native permission '
            'request and reviewed command/path metadata. A successful write alone does not prove permission handling.')
        row['proposed_effects'] += ' One report.json in the authorized sibling directory; no policy change or extra filesystem writes.'
value['token_accounting']['operational_variant_not_yet_authorized']['interrupt_threshold'] = 100000
value['token_accounting']['operational_variant_not_yet_authorized']['meaning'] = (
    'Pending clarification only: stop new admissions and request preventive interruption at '
    '100000 reported aggregate tokens; still no guarantee actual usage stays below200000. '
    'Elapsed time, account authentication and this revised proposal are not execution authorization.')
value['revision_note'] = (
    'Adds one useful sibling report per lane without broadening native policy; keeps no-request '
    'case pending. Pins SVC07 candidate wheel hashes as unqualified candidates. Old proposal '
    'and manifest remain byte-for-byte immutable. No task, provider or fixture execution.')
value['blocking_preconditions_before_execution_request'][0] = 'Candidate SVC07 wheel hashes are pinned, but final installed qualification/import proofs remain pending for M1 execution.'
with (PUBLIC / 'm1-codex-campaign-proposal-v2.json').open('x', encoding='utf-8', newline='\n') as stream:
    stream.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n')

text = '''# Proposta M1 v2 — entrega útil e permissão nativa

Esta revisão substitui apenas o roteiro proposto. A v1 e seu manifesto permanecem intactos. Nenhum serviço, provider, binário Codex ou fixture foi executado; a pergunta sobre o teto rígido/operacional de tokens ainda não teve resposta.

O trabalho agora lê `numbers.csv` do projeto e produz `report.json` com `row_count=4`, `sum=10` e SHA-256 do arquivo de entrada. Cada topologia tem um destino próprio: `m1-campaign/deliverables/local/report.json` ou `m1-campaign/deliverables/connector/report.json`, irmãos dos respectivos diretórios de projeto, todos dentro do novo Temp autorizado da campanha. Os diretórios de entrega só serão criados após autorização; arquivos existentes nunca serão sobrescritos.

O destino deve estar fora dos writable roots efetivos do projeto. Isso pode provocar um pedido nativo legítimo ao tentar gravar, sem mudar sandbox, permissões, writable roots ou política global. A futura decisão humana cobre somente o comando realmente apresentado e os dois caminhos exatos daquela etapa. Uma recusa não pode ser contornada por outro tool, caminho ou comando.

Não há garantia de que a política efetiva produza um pedido. Se a gravação for admitida diretamente, o resultado útil pode ser validado, mas a etapa de decisão nativa M1 continua pendente. O teste não transforma um texto do modelo ou uma gravação bem-sucedida em prova de aprovação.

Mantêm-se os ciclos local e Connector, identidade humana do operador, checkpoints anteriores à submissão, perda de resposta declarada, recuperação pelos mesmos IDs, retorno ao resultado e limpeza canônica. O máximo continua sendo seis admissões produtivas, contando testes de conexão; não foram adicionados turnos para perseguir uma aprovação.

Os três wheels SVC07 candidatos agora têm hashes exatos no JSON, mas isso não representa aceite final da qualificação em curso. A proposta das duas tarefas Windows fica separada: é infraestrutura vazia, sem provider ou inferência. Autorizar essas tarefas não autoriza automaticamente M1.

O teto rígido de 200 mil tokens continua sem garantia no fluxo atual. A alternativa operacional em esclarecimento interromperia preventivamente aos 100 mil reportados e recusaria novos trabalhos; atrasos de observação/interrupção ainda podem causar overshoot. Não haverá goal persistente nem uso da conta antes da resposta e da autorização explícita.

O JSON é o roteiro completo revisado, com caminhos absolutos, prompts, gates, comandos, pins candidatos e vínculos de hash à v1. Esta nota não substitui suas condições.
'''
with (PUBLIC / 'm1-codex-campaign-proposal-v2.md').open('x', encoding='utf-8', newline='\n') as stream:
    stream.write(text)
print(json.dumps({'proposal': str(PUBLIC / 'm1-codex-campaign-proposal-v2.json'),
    'sha256': hashlib.sha256((PUBLIC / 'm1-codex-campaign-proposal-v2.json').read_bytes()).hexdigest(),
    'previous_manifest_unchanged': value['prior_public_manifest_sha256'] == '36cf3f603c80e6ef154a195637043f957a8e256844b58adfaa7f98a561a340ee'}))
