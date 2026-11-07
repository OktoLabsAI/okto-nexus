from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json
import re
import shutil

parser = argparse.ArgumentParser()
parser.add_argument('source', type=Path)
args = parser.parse_args()
repo = Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
target = repo / 'plans/agent_ops/evidence/r3-dx04-native-startup'
manifest = json.loads((args.source / 'artifact-manifest.json').read_text(encoding='utf-8'))
assert {p.relative_to(args.source).as_posix() for p in args.source.rglob('*') if p.is_file()} == set(manifest['files']) | {'artifact-manifest.json'}
for name, record in manifest['files'].items():
    path = args.source / name
    assert path.resolve().is_relative_to(args.source.resolve())
    assert hashlib.sha256(path.read_bytes()).hexdigest() == record['sha256']
    assert path.stat().st_size == record['bytes']
assert not target.exists()
shutil.copytree(args.source, target / 'probe')
shutil.copy2(__file__, target / 'close_milestone.py')
prefix = target.relative_to(repo).as_posix()
note = '''
## 2026-11-07 — inicialização nativa isolada de DX-04

O ParticipantLaunch instalado iniciou o Codex 0.167.0 em perfil descartável,
com console próprio e chave Nexus sintética importada por stdin para um alvo
exclusivo do cofre Windows. A tela de login foi observada por rótulos fixos;
nenhuma entrada, credencial de provedor ou solicitação produtiva foi enviada.
Não foi observada autenticação MCP nativa. O único initialize HTTP 401 foi o
controle negativo sem bearer do próprio harness.

A tentativa 001 falhou antes de CreateProcess: o binding de CreateJobObject
não aceitou nome None. A correção exclusiva do harness passou no diagnóstico
benigno com CLI --help, TTY nos três streams e Job vazio ao terminar. A tentativa
002 iniciou o cliente, mas o watcher registrou PermissionError de causa não
demonstrada. O resultado original continua UNCONFIRMED. O Job foi encerrado à
força com código 125 e zero processos ativos; o listener do Server foi fechado
e o alvo próprio do cofre ficou ausente. O agregado cleanup_confirmed=false
é preservado, assim como a ausência dos pós-checks abortados no runner.

A conferência posterior confirmou os hashes dos inputs da tentativa 002. As
contagens finais canônicas foram lidas em modo somente leitura; não há baseline
retido para afirmar igualdade antes/depois. Esses fatos não substituem os
pós-checks ausentes nem promovem o resultado original.

DX-04 permanece IMPLEMENTED: startup, vault e controle negativo não comprovam
consumo da credencial pelo cliente. Não houve alteração de produto, inferência,
acesso à conta autenticada, registro de serviço nativo ou novo aceite de M1.
As propostas e perguntas pendentes de autorização/orçamento continuam válidas.
Evidência: `plans/agent_ops/evidence/r3-dx04-native-startup/milestone.md`.
'''
(target / 'milestone.md').write_text(note.lstrip(), encoding='utf-8')
ledger_path = repo / 'plans/agent_ops/ledger.json'
ledger = json.loads(ledger_path.read_text(encoding='utf-8'))
task = ledger['tasks']['DX-04']
assert task['status'] == 'IMPLEMENTED'
task['result'] = ('Importação protegida, vault, isolamento e negativos permanecem verificados. '
    'O launcher instalado iniciou Codex0.167.0 isolado e exibiu login; não houve cadeia MCP '
    'autenticada. Run002 UNCONFIRMED por PermissionError no watcher; nenhum defeito de produto demonstrado.')
task['remaining_evidence'] = ('Observar autenticação MCP do cliente suportado iniciado pelo ParticipantLaunch '
    'com referência protegida. Nesta tentativa isolada, a tela de login precedeu qualquer MCP positivo. '
    'Acesso à conta real depende de autorização específica; um turno pago não é requisito literal de DX04.')
task['limitations'] = [
    'Run001 falhou no harness antes de CreateProcess; delta benigno validado e preservado.',
    'Run002: startup/login observados, watcher PermissionError sem causa demonstrada; somente controle MCP401.',
    'Job vazio após contenção forçada125, listener fechado e cofre próprio ausente; resultado agregado UNCONFIRMED preservado.',
    'Não comprova autenticação MCP, login de provedor, trabalho, serviço de usuário ou M1.',
]
task['reconciliation']['current_scope'] = task['result']
task['reconciliation']['evidence'] = prefix + '/milestone.md'
task['tests'] = sorted(set(task['tests'] + [prefix + '/artifact-manifest.json', prefix + '/milestone.md']))
task['native_startup_probe'] = dict(status='UNCONFIRMED', native_version='0.167.0',
    native_mcp_confirmed=False, provider_credentials_supplied=False, provider_inference_performed=False,
    evidence=prefix + '/artifact-manifest.json')
ledger['campaigns']['r3_dx04_native_startup'] = dict(status='UNCONFIRMED', accepted_tasks=[],
    attempts=2, native_startup_attempts=1, benign_console_diagnostic='PASS',
    product_changed=False, native_mcp_confirmed=False, evidence=[prefix + '/milestone.md', prefix + '/artifact-manifest.json'])
ledger['updated_at'] = datetime.now(timezone.utc).isoformat()
ledger['history'].append(dict(date='2026-11-07', milestone='Isolated native participant startup',
    status='UNCONFIRMED', summary='Preserved harness failure, benign correction and native login gate. DX04 remains IMPLEMENTED; no provider use or product change.',
    evidence=[prefix + '/milestone.md']))
ledger_path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
for name in ('LEDGER_CODEX_NEXUS_INTEGRACAO_ATENCAO_ONBOARDING.md', 'plans/agent_ops/implementation-report.md'):
    with (repo / name).open('a', encoding='utf-8') as stream:
        stream.write(note)
with (repo / '.gitattributes').open('a', encoding='utf-8') as stream:
    stream.write(prefix + '/** -text -whitespace\n')
patterns = [rb'\b(?:nxs_|nxobs_|nxsept_|nxt4_|nxc4_)[A-Za-z0-9_-]{20,}',
            rb'\b(?:sk-proj-|sk-ant-|sk-)[A-Za-z0-9_-]{24,}', rb'\b(?:ghp_|github_pat_)[A-Za-z0-9_]{25,}']
assert not [(p.name, hashlib.sha256(m.group()).hexdigest()) for p in target.rglob('*') if p.is_file()
            for pattern in patterns for m in re.finditer(pattern, p.read_bytes())]
files = {p.relative_to(target).as_posix(): dict(sha256=hashlib.sha256(p.read_bytes()).hexdigest(), bytes=p.stat().st_size)
         for p in sorted(target.rglob('*')) if p.is_file()}
(target / 'artifact-manifest.json').write_text(json.dumps(dict(files=files,
    scope='Finite public startup evidence; private homes, databases, configs and raw logs excluded'), indent=2) + '\n', encoding='utf-8')
print(json.dumps(dict(status='UNCONFIRMED', dx04='IMPLEMENTED', artifacts=len(files))))
