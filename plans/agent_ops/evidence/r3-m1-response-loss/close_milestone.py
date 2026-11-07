from pathlib import Path
from datetime import datetime, timezone
import hashlib,json,re,shutil,xml.etree.ElementTree as ET

repo=Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
source=Path('C:/Users/jpamb/AppData/Local/Temp/m1-response-loss-4n_e6nii/public')
target=repo/'plans/agent_ops/evidence/r3-m1-response-loss'
m=json.loads((source/'artifact-manifest.json').read_text())
assert {p.relative_to(source).as_posix() for p in source.rglob('*') if p.is_file()}==set(m['files'])|{'artifact-manifest.json'}
for name,record in m['files'].items():
    raw=(source/name).read_bytes()
    assert hashlib.sha256(raw).hexdigest()==record['sha256'] and len(raw)==record['bytes']
run=source/'synthetic-run-ncmurvj3'
cases=list(ET.parse(run/'synthetic-results.xml').iter('testcase'))
assert len(cases)==11 and not any(c.find(k) is not None for c in cases for k in ('error','failure','skipped'))
assert (run/'input-hashes-before.json').read_bytes()==(run/'input-hashes-after.json').read_bytes()
assert not target.exists()
shutil.copytree(source,target/'preparation')
shutil.copy2(__file__,target/'close_milestone.py')
prefix=target.relative_to(repo).as_posix()
note='''
## 2026-11-07 — driver finito de perda de resposta M1

Preparado driver de cliente que descarta uma resposta de admissão e uma de
decisão, somente após a confirmação canônica correspondente. Reservas duráveis
impedem novo POST; reconstrução usa os mesmos checkpoints e IDs. Uma reserva
forwarding/unconfirmed deixada por crash bloqueia novas admissões/decisões,
mantendo inspeção e interrupt/close canônicos disponíveis.

No build final, 11 casos únicos passaram, incluindo integração com Nexus/Core
instalados, ASGI e SQLite reais e executor nativo sintético. A integração exige
um POST de trabalho, um POST de decisão, um turno e uma resposta sintéticos,
os mesmos IDs após perda, resultado e close. Foram conferidos 992 arquivos
antes/depois e ausência de módulos de produto importados do checkout.
Falhas anteriores de guard de teste e prefixo de rota permanecem preservadas;
a correção do crash foi seguida de requalificação dos 11 casos finais.

Isso prepara instrumentação da campanha, sem qualificar M1, Connector real,
login, inferência ou serviço do SO. A cota de seis envios deste wrapper ainda
não inclui setup:test automaticamente; faltam coletor e integração do runner
antes do primeiro teste produtivo. Nenhuma credencial pessoal ou provider foi
usado, nenhum arquivo de produto alterado, nenhum aceite promovido.
Evidência: `plans/agent_ops/evidence/r3-m1-response-loss/preparation/README.md`.
'''
(target/'milestone.md').write_text(note.lstrip(),encoding='utf-8')
lp=repo/'plans/agent_ops/ledger.json'
ledger=json.loads(lp.read_text(encoding='utf-8'))
ledger['campaigns']['m1_codex_real']['response_loss_preparation']=dict(status='SYNTHETIC_INSTALLED_VERIFIED',
    final_unique_passes=11,evidence=prefix+'/artifact-manifest.json',
    limit='Driver only; setup accounting and controller integration remain pending. No productive M1 acceptance.')
ledger['updated_at']=datetime.now(timezone.utc).isoformat()
ledger['history'].append(dict(date='2026-11-07',milestone='Finite M1 response-loss driver',status='PREPARED',
    summary='11 final synthetic/installed cases qualify client instrumentation and crash fences;992inputs unchanged. No product/provider/service change; runner integration remains pending.',
    evidence=[prefix+'/milestone.md']))
lp.write_text(json.dumps(ledger,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
for name in ('LEDGER_CODEX_NEXUS_INTEGRACAO_ATENCAO_ONBOARDING.md','plans/agent_ops/implementation-report.md'):
    with (repo/name).open('a',encoding='utf-8') as f:f.write(note)
with (repo/'.gitattributes').open('a',encoding='utf-8') as f:f.write(prefix+'/** -text -whitespace\n')
patterns=[rb'\b(?:nxs_|nxobs_|nxsept_|nxt4_|nxc4_)[A-Za-z0-9_-]{20,}',rb'\b(?:sk-proj-|sk-ant-|sk-)[A-Za-z0-9_-]{24,}']
assert not [(p.name,hashlib.sha256(match.group()).hexdigest()) for p in target.rglob('*') if p.is_file()
            for pattern in patterns for match in re.finditer(pattern,p.read_bytes())]
files={p.relative_to(target).as_posix():dict(sha256=hashlib.sha256(p.read_bytes()).hexdigest(),bytes=p.stat().st_size)
       for p in sorted(target.rglob('*')) if p.is_file()}
(target/'artifact-manifest.json').write_text(json.dumps(dict(files=files,scope='Finite synthetic campaign instrumentation only'),indent=2)+'\n')
print(json.dumps(dict(final_unique_passes=11,public_payloads=len(files))))
