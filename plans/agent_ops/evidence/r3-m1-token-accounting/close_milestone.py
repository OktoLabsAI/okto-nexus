from pathlib import Path
from datetime import datetime, timezone
import hashlib,json,re,shutil,xml.etree.ElementTree as ET

repo=Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
source=Path('C:/Users/jpamb/AppData/Local/Temp/m1-token-collector-a_vy2tgw/public-final')
target=repo/'plans/agent_ops/evidence/r3-m1-token-accounting'
manifest=json.loads((source/'artifact-manifest.json').read_text())
assert {p.relative_to(source).as_posix() for p in source.rglob('*') if p.is_file()}==set(manifest['files'])|{'artifact-manifest.json'}
for name,record in manifest['files'].items():
    raw=(source/name).read_bytes()
    assert hashlib.sha256(raw).hexdigest()==record['sha256'] and len(raw)==record['bytes']
cases=list(ET.parse(source/'final.xml').iter('testcase'))
assert len(cases)==40 and not any(c.find(k) is not None for c in cases for k in ('failure','error','skipped'))
assert not target.exists()
shutil.copytree(source,target/'preparation')
shutil.copy2(__file__,target/'close_milestone.py')
prefix=target.relative_to(repo).as_posix()
old=repo/'plans/agent_ops/evidence/r3-m1-execution-context/m1-codex-campaign-proposal-v5.json'
proposal=json.loads(old.read_text(encoding='utf-8'))
proposal['revision']=6
proposal['token_accounting']['accounting_algorithm']=[
    'Arm and persist the serial campaign reservation before any setup test or productive effect. Include every setup/work/continuation in the global maximum of six.',
    'Replay committed work events through the existing page contract, validating scope, epoch, cursors, watermark and gap. Observe standalone setup journals as a distinct owned source; do not invent canonical binding fields absent there.',
    'Keep a monotone high-water total.totalTokens for each actual native thread with explicit fresh/pre-campaign baseline. Resume/handover never zeros usage or counts the same cumulative total twice.',
    'Sum high-water deltas across the owned sources once. Do not add last, cached or reasoning subfields to totalTokens.',
    'A work request may settle observationally only after its correlated turn start, terminal outcome, at least one usage observation and caught-up gap-free replay. This is coverage of the observed prefix, not proof of a final provider/billing counter. Continue monitoring earlier threads for delayed usage.',
    'Missing usage for the completed turn, missing start/terminal, unknown source, cursor gap, regression/reset or malformed data blocks new admissions. Preserve known minimum and request canonical interrupt/close or owned service stop as appropriate to the active scope.',
    'Use the existing preventive100000 observed-token threshold and120-second serial deadline. Additional500000 tolerance over the original200000 does not create a native hard cap or authorize extra turns.'
]
proposal['token_accounting']['collector_preparation']=dict(evidence=prefix+'/preparation/README.md',
    final_unique_tests=40, controller_integration_complete=False,
    scope='Pure deterministic work-event collector with caller-owned persistence; standalone setup source and live controller still separate.')
proposal['token_accounting']['response_loss_preparation']='plans/agent_ops/evidence/r3-m1-response-loss/preparation/README.md'
proposal['blocking_preconditions_before_execution_request'][0]=(
    'Integrate the tested collector and response-loss driver with the standalone setup-journal observer, global serial reservation and owned canonical abort. Validate this finite composition against installed synthetic flows before provider execution.')
proposal['supersedes_proposal_sha256']=hashlib.sha256(old.read_bytes()).hexdigest()
proposal['supersedes_proposal_path']=old.relative_to(repo).as_posix()
proposal['revision_note']='Qualified pure accounting component,40final tests;11response-loss cases already retained. Clarified operational observed-prefix policy after user budget tolerance. No final-usage marker or atomic cap is invented; full setup/controller integration and execution approval remain pending.'
(target/'m1-codex-campaign-proposal-v6.json').write_text(json.dumps(proposal,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
note='''
## 2026-11-07 — contabilidade operacional M1

Coletor determinístico preparado e verificado em 40 casos finais: contagem
cumulativa por thread sem duplicação no replay, escopos/epochs/cursors/gaps,
reservas seriais antes de runtime.start, vínculo posterior aos mesmos IDs,
seis reservas globais, recusa em stream aposentado e preventiva de 100 mil.
A rodada anterior de 39 casos e seus inputs foi preservada; não são 79 casos.
As transições são puras; persistência/dispatch pertencem ao controlador.
Não houve HTTP, provider, processo nativo ou acesso a credenciais.

A proposta v6 esclarece o limite operacional aceito: depois de turno terminal,
ao menos uma observação de uso correlacionada e replay atualizado sem gaps,
o valor continua sendo mínimo observado, não contador final/faturado. A
monitoração de threads anteriores continua para atualizações tardias. Ausência
de uso, regressão, gap ou fonte desconhecida impede nova admissão. O schema
nativo não oferece marcador de uso final nem corte atômico, e não se inventa
essa garantia. Mantêm-se 700 mil de tolerância total e preventiva de 100 mil.

O journal privado do setup é uma fonte distinta, sem os campos do scope da
API pública de trabalho. Sua observação e a integração global com reserva,
driver de perda e abort canônico ainda estão em preparação. Este marco não
qualifica M1 nem autoriza conta, inferência ou serviço; nenhum aceite promovido.
Evidência: `plans/agent_ops/evidence/r3-m1-token-accounting/preparation/README.md`.
'''
(target/'milestone.md').write_text(note.lstrip(),encoding='utf-8')
lp=repo/'plans/agent_ops/ledger.json'
ledger=json.loads(lp.read_text(encoding='utf-8'))
ledger['campaigns']['m1_codex_real'].update(proposal=prefix+'/m1-codex-campaign-proposal-v6.json',
    token_collector_preparation=dict(status='PURE_CONTRACT_VERIFIED',final_unique_passes=40,
        evidence=prefix+'/artifact-manifest.json',controller_integration_complete=False))
ledger['updated_at']=datetime.now(timezone.utc).isoformat()
ledger['history'].append(dict(date='2026-11-07',milestone='M1 operational token accounting component',status='PREPARED',
    summary='40final pure cases qualify replay, reservation, namespace and retired-stream guards; initial39 retained separately. Clarified observed-prefix policy; setup/controller integration remains pending. No provider use or acceptance promotion.',
    evidence=[prefix+'/milestone.md']))
lp.write_text(json.dumps(ledger,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
for name in ('LEDGER_CODEX_NEXUS_INTEGRACAO_ATENCAO_ONBOARDING.md','plans/agent_ops/implementation-report.md'):
    with (repo/name).open('a',encoding='utf-8') as stream:stream.write(note)
with (repo/'.gitattributes').open('a',encoding='utf-8') as stream:stream.write(prefix+'/** -text -whitespace\n')
patterns=[rb'\b(?:nxs_|nxobs_|nxsept_|nxt4_|nxc4_)[A-Za-z0-9_-]{20,}',rb'\b(?:sk-proj-|sk-ant-|sk-)[A-Za-z0-9_-]{24,}']
assert not [(p.name,hashlib.sha256(match.group()).hexdigest()) for p in target.rglob('*') if p.is_file()
    for pattern in patterns for match in re.finditer(pattern,p.read_bytes())]
files={p.relative_to(target).as_posix():dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest())
    for p in sorted(target.rglob('*')) if p.is_file()}
(target/'artifact-manifest.json').write_text(json.dumps(dict(files=files,scope='Pure accounting preparation, not full live campaign control'),indent=2)+'\n')
print(json.dumps(dict(final_unique_passes=40,revision=6,public_payloads=len(files))))
