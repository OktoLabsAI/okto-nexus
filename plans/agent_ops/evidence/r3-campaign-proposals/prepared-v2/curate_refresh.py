"""Curate a closed allowlist only; never copy wheels, profiles, homes or stores."""
from pathlib import Path
import hashlib
import json
import re
import shutil

ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT / 'public'
NATIVE = ROOT / 'native'
DEST = PUBLIC / 'native'
DEST.mkdir(exist_ok=False)

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

native_files = [
    'inspect_installed.py', 'prepare_proposal.py', 'finalize_proposal.py',
    'environment.json', 'environment-preparation.json', 'source-heads.json',
    'installed-proof.json', 'pythonw-import-proof.json', 'read-only-checks.json',
    'native-service-campaign-proposal.json',
    'venv-create.log', 'offline-install.log', 'pip-check.log', 'proposal-readonly-checks.log',
]
checks = json.loads((NATIVE / 'read-only-checks.json').read_bytes())
assert len(checks) == 8 and all(row['returncode'] == 0 for row in checks)
for name in (
    'installed-inspection', 'pythonw-imports', 'nexus-service-help', 'connector-service-help',
    'connector-service-install-help', 'connector-daemon-help', 'connector-daemon-start-help', 'connector-daemon-stop-help',
):
    native_files.extend([name + '.stdout.txt', name + '.stderr.txt'])
for name in native_files:
    source = NATIVE / name
    shutil.copyfile(source, DEST / name)
    assert sha(source) == sha(DEST / name)
for name in ('prepare_refresh.py', 'refine_m1.py', 'curate_refresh.py'):
    shutil.copyfile(ROOT / name, PUBLIC / name)

proposal = json.loads((DEST / 'native-service-campaign-proposal.json').read_bytes())
installed = json.loads((DEST / 'installed-proof.json').read_bytes())
assert len(proposal['steps']) == 24
assert all(not item['exists'] for item in installed['task_observations'].values())
assert all(item['exact_source_wheel_install'] and item['exact_wheel_install'] for item in installed['packages'].values())
prior_m1 = Path('C:/Users/jpamb/AppData/Local/Temp/m1-codex-campaign-proposal-ynzvp8yx/public/artifact-manifest.json')
assert sha(prior_m1) == '36cf3f603c80e6ef154a195637043f957a8e256844b58adfaa7f98a561a340ee'

note = f'''# Refresh de propostas — somente preparação

M1 v2 e Windows duas tarefas são propostas separadas. Nenhum aceite M1, execução nativa de provider ou mutação de serviço foi feito. A proposta Windows usa os três wheels candidatos SVC07; a qualificação instalada final continua a cargo do root e não é inferida dos checks desta pasta.

Checks fechados: venv próprio sem system-site-packages, instalação offline de dependências previamente pinadas (MCP1.30.0), pip check, oito import/help checks, igualdade source/wheel/install de691arquivos Nexus,124Connector e166Core, e leitura dos dois nomes exatos abaixo. Ambos estavam ausentes. Nenhum registro, start, enable, stop ou delete de Task Scheduler foi chamado.

- Nexus: `{proposal['task_names']['nexus']}`
- Connector: `{proposal['task_names']['connector']}`
- Loopback aprovado apenas como proposta:127.0.0.1:{proposal['port']}.
- Roteiro:24ações finitas,12por componente (install, repeated install, start, reuse, disable, stop, recusa de start desabilitado, enable, start, restart, stop, uninstall).

O primeiro driver concluiu todos os oito checks e as duas leituras, mas não encontrou git no PATH isolado. O log bruto permanece byte a byte, inclusive sua codificação original. O finalizador usou esses reports fechados e metadata de repositório obtida separadamente; não repetiu imports ou acesso nativo. Isso foi falha da preparação, não do produto ou campanha.

O M1 v1/manifesto anterior permaneceu igual. A v2 acrescenta report.json em diretório irmão descartável, sem ampliar política ou sandbox. Se não surgir pedido nativo verdadeiro, esse caso permanece pendente. A pergunta sobre200mil rígidos versus interrupção preventiva aos100mil reportados ainda não representa resposta nem autorização.

Arquivos desta pasta são curados por allowlist. Wheels, venv, profiles, homes, bancos e material de autenticação estão excluídos. Os scripts são evidência revisável de preparação; não são um autorizador nem runner da campanha.
'''
for before, after in {
    'MCP1.30.0': 'MCP 1.30.0', 'de691arquivos': 'de 691 arquivos', ',124Connector': ', 124 Connector',
    'e166Core': 'e 166 Core', 'proposta:127': 'proposta: 127', 'Roteiro:24ações': 'Roteiro: 24 ações',
    ',12por': ', 12 por', 'sobre200mil': 'sobre 200 mil', 'aos100mil': 'aos 100 mil',
}.items():
    note = note.replace(before, after)
(PUBLIC / 'README.md').write_text(note, encoding='utf-8', newline='\n')
files = []
for path in sorted(PUBLIC.rglob('*')):
    if not path.is_file():
        continue
    assert path.suffix in ('.json', '.md', '.py', '.log', '.txt')
    payload = path.read_bytes()
    assert not re.search(rb'nxs_[A-Za-z0-9_-]{24,}', payload), path.name
    if path.suffix == '.json':
        json.loads(payload)
    files.append(dict(path=path.relative_to(PUBLIC).as_posix(), bytes=len(payload), sha256=sha(path)))
aggregate = hashlib.sha256(json.dumps(files, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
manifest = dict(format='okto.campaign-proposal-refresh-manifest', revision=1, status='CANDIDATES_PREPARED_NOT_AUTHORIZED_NOT_RUN',
    files=files, aggregate_sha256=aggregate, native_task_mutations=0, provider_calls=0,
    native_task_queries=2, checks_passed=8, source_wheel_installed_equal={key: row['file_count'] for key,row in installed['packages'].items()},
    prior_m1_manifest_sha256=sha(prior_m1),
    native_proposal_sha256=sha(DEST / 'native-service-campaign-proposal.json'),
    m1_v2_proposal_sha256=sha(PUBLIC / 'm1-codex-campaign-proposal-v2.json'),
    excluded=['venv', 'wheels', 'profiles', 'homes', 'databases', 'personal credentials'], redactions=0,
    limits=['Candidate hashes are not final installed campaign acceptance.', 'No native service lifecycle or provider activity was executed.', 'Strict200k token guarantee and execution authorization remain unresolved.'])
(PUBLIC / 'artifact-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
print(json.dumps(dict(public=str(PUBLIC), files=len(files), aggregate_sha256=aggregate,
    manifest_sha256=sha(PUBLIC / 'artifact-manifest.json'), native_proposal_sha256=manifest['native_proposal_sha256'],
    m1_v2_proposal_sha256=manifest['m1_v2_proposal_sha256'], port=proposal['port'], task_names=proposal['task_names'])))
