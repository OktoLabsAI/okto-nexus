from pathlib import Path
import hashlib,json,re,shutil
ROOT=Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
OUT=ROOT/'plans/agent_ops/evidence/r3-compatibility-boundaries'
TRACE=Path('C:/Users/jpamb/AppData/Local/Temp/r3-final-traceability-n905rp1o')
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(p,o): p.write_text(json.dumps(o,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
assert sha(TRACE/'artifact-manifest.json')=='181fefcc510bd8b80c7a664042f1d173bfad224422629a0884d715891c6e726f'
manifest=json.loads((TRACE/'artifact-manifest.json').read_text(encoding='utf-8'))['files']
for name,meta in manifest.items():
    assert sha(TRACE/name)==meta['sha256'],name
    assert not re.search(rb'\b(?:nxs_|nxobs_|nxsept_|nxt4_|nxc4_)[A-Za-z0-9_-]{20,}',(TRACE/name).read_bytes()),name
(OUT/'traceability').mkdir()
for name in [*manifest,'artifact-manifest.json']:
    shutil.copyfile(TRACE/name,OUT/'traceability'/name)
summary='''# R3 — compatibilidade, importação e integridade dos pacotes

RG-06, RG-07 e RG-08 qualificados no snapshot atual Windows; AC-07 atendido pelas fronteiras verificadas e dependências reproduzíveis. Nenhum código de aplicação ou wheel mudou. Documentação de conexão inclui a matriz de versões; guia da campanha Windows passa a apontar a proposta vigente ainda não autorizada/não executada.

## Compatibilidade instalada

Quatro pares executados via GET público real `/v1/connections/protocol`: Connector 0.0.11/Core 0.0.13 com Nexus 0.3.2/Core 0.0.13, e Connector 0.0.12/Core 0.0.14 com Nexus 0.3.3/Core 0.0.14, são compatíveis. Os dois pares cruzados recusam `VERSION_INCOMPATIBLE`, stage `protocol`, `possible_effect=false`. A igualdade da revisão de wire não dispensa igualdade da versão Core.

Foram exatamente quatro GETs, sem credenciais, query ou corpo. As 143 tabelas do servidor antigo e 160 do atual permaneceram idênticas; fixtures HTTP saíram normalmente e seus PIDs reais estavam ausentes. Aplicação instalada e SQLite reais, com lifespan nativo desligado. Não são execução autenticada, provider, serviço nativo, cliente MCP externo, TLS ou M1/M2. Histórico foi construído de commits exatos em Temp; tentativas de preparação recusadas estão preservadas. Não houve downgrade de banco pessoal nem alteração das cercas de compatibilidade.

## Imports e fronteiras

131 módulos Core importados sob guards ativos; 165 arquivos iguais entre fonte, wheel e instalação. Auditoria complementar usa ambiente/home sintéticos, sem valores de credencial, stdin DEVNULL, stdout bruto retido e nove controles negativos. Zero evento proibido, lookup originado no Core ou chamada às 19 APIs nativas guardadas. Os 255 lookups benignos de dependências (oito pares nome/caller) e nove bindings de console Click ficam explícitos. Recusas iniciais de GetStdHandle foram preservadas; a exceção final permite apenas console/buffer revisados.

As fontes Nexus (513 Python) e Connector (122 Python) não importam a aplicação irmã; quatro chamadas dinâmicas foram revisadas e ficam no próprio namespace. O verificador Core recusa dependências não declaradas e cargas dinâmicas fora do registro. A auditoria cobre o código/import observado e as superfícies instrumentadas; não é tracer universal de extensões C/syscalls ou qualificação de execução nativa.

## Empacotamento e rastreabilidade

Nexus: 690 arquivos, incluindo 167 migrações e sete recursos UI. Connector: 123 arquivos. Core: 165 arquivos, incluindo 31 schemas e dois recursos JS. Nenhum recurso-fonte omitido; payloads iguais aos artefatos instalados/candidatos atuais. A instalação CI declarada com MCP 1.30.0 e pip check aprovado permanece a prova de dependências; o browser histórico em MCP 1.29.1 continua só como evidência das interações observadas.

Revisão somente leitura verificou 1.384 entradas de manifests (incluindo sobreposições), 724 referências locais e as 71 identidades aprovadas do milestone anterior. Os 22 casos de proteção mapeados são evidência histórica de oito funções, não novas execuções. Dois arquivos de proveniência Herdr fora do manifesto principal estão inventariados no suplemento público; nenhum dado privado foi acrescentado.

RG-09 permanece em progresso: mixed e modos de sessão têm allowlists explícitas; RG03/RG05 usam fixtures temporárias mas herdaram ambiente, limite que não é apagado por outra campanha mais forte. AC-09 permanece pendente da reconciliação final de tarefas/cenários nomeados, em execução somente leitura. AC-10 mantém o limite de credencial histórica/commits anteriores já registrado. RG-05 continua parcial; M1/M2, clientes reais, provedor e campanhas nativas continuam abertos. Nenhum novo requisito de tracer universal, TLS/dois hosts ou plataforma adicional foi criado.

Reprodução e prova: compatibility/qualfication.json (arquivo correto: `compatibility/qualification.json`), core/report.json, core/stdout.json e traceability/traceability.json. Os manifests de origem são preservados; o manifesto deste diretório liga todos os bytes públicos. O plano fixo e IDs 59/132/28/17 permanecem iguais.
'''.replace('compatibility/qualfication.json (arquivo correto: `compatibility/qualification.json`)','compatibility/qualification.json')
(OUT/'milestone.md').write_text(summary,encoding='utf-8')
shutil.copyfile(__file__,OUT/'close-milestone.py')
manifest={p.relative_to(OUT).as_posix():dict(sha256=sha(p),bytes=p.stat().st_size) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='artifact-manifest.json'}
# Include nested manifests too; only the outer manifest is excluded.
for p in OUT.rglob('artifact-manifest.json'):
    if p.parent!=OUT: manifest[p.relative_to(OUT).as_posix()]=dict(sha256=sha(p),bytes=p.stat().st_size)
dump(OUT/'artifact-manifest.json',dict(format='r3-compatibility-boundaries-v1',files=manifest))
path=ROOT/'plans/agent_ops/ledger.json';l=json.loads(path.read_text(encoding='utf-8'))
sets={k:set(l[k]) for k in ['tasks','scenarios','invariants','completion_criteria']}
prefix='plans/agent_ops/evidence/r3-compatibility-boundaries/'
ev=[prefix+x for x in ['milestone.md','artifact-manifest.json']]
for key,specific,result in [
 ('RG-06','core/report.json','All 131 current Core modules imported on Windows under socket/process/file/environment/native-credential guards; nine negative controls and verbatim stdout retained. Current literal/dynamic application imports stay within declared boundaries. No credential resolution or adapter execution; no universal native tracing claim.'),
 ('RG-07','compatibility/qualification.json','Four exact installed public-protocol version pairs qualified. Aligned Core versions accepted; old/new crossed pairs refused VERSION_INCOMPATIBLE at protocol before effects. Four uncredentialed GETs; 143/160 database tables unchanged. Documented separately from external MCP client/provider compatibility.'),
 ('RG-08','traceability/payload-verification.json','Current Nexus/Connector/Core wheels contain all 690/123/165 source package files, including UI, 167 migrations, 31 Core schemas and resources. Current isolated installed CI payload and declared MCP1.30 solve are verified; no sibling checkout dependency.')]:
    row=l['scenarios'][key];row.update(status='VERIFIED',result=result)
    row['evidence']=sorted(set(row['evidence']+ev+[prefix+specific]))
row=l['completion_criteria']['AC-07'];row['status']='VERIFIED'
row['result']='Current installed Windows dependencies resolve with MCP1.30 and pip check; exact coordinated pins/payloads and Core/Nexus/Connector import boundaries are qualified. Historical browser environment is not used as dependency-solve evidence.'
row['evidence']=sorted(set(row['evidence']+ev+[prefix+'core/report.json',prefix+'traceability/payload-verification.json','plans/agent_ops/evidence/r3-qualification-readiness/ci/reports.json']))
row=l['scenarios']['RG-09'];row['status']='IN_PROGRESS'
row['evidence']=sorted(set(row['evidence']+ev+[prefix+'traceability/traceability.json']))
row.setdefault('subscopes',{})['current_mixed_session_protocol_and_import_campaign_isolation']='VERIFIED'
row['result']='Recorded temporary scopes and explicit environment allowlists qualify the named mixed/session/protocol/import campaigns. RG03/RG05 inherited environment; do not generalize stronger isolation proof to them. Future authorized native/provider campaigns require their own isolation/cleanup proof.'
trace=json.loads((OUT/'traceability/traceability.json').read_text(encoding='utf-8'))
for section,rows in [('completion_criteria',trace['completion_criteria']),('invariants',trace['invariants'])]:
    for item in rows:
        key=item['id'];row=l[section][key]
        refs=[x for x in item.get('evidence',[]) if x.startswith('plans/') and (ROOT/x).is_file()]
        row['evidence']=sorted(set(row['evidence']+refs+[prefix+'traceability/traceability.json']))
l['campaigns']['r3_compatibility_import_packaging']=dict(status='VERIFIED',protocol_pairs=4,imported_core_modules=131,negative_controls=9,product_changed=False,scope='Current Windows installed protocol/import/package boundaries; not global acceptance',evidence=ev)
l['milestones']['PR-10']['evidence']=sorted(set(l['milestones']['PR-10']['evidence']+ev))
l['history'].append(dict(date='2026-11-07',milestone='PR-10',status='IN_PROGRESS',summary='Qualified four installed old/new protocol pairs, 131 guarded Core imports with nine negative controls, and complete 690/123/165 package payloads. RG06/07/08 and AC07 verified in current Windows scope. Documentation now states version refusals and points to the current unexecuted service proposal. Read-only trace inventory linked; RG09, AC09/10 and real M1/M2 remain open; task/scenario reconciliation proceeds without reruns.',evidence=ev))
l['updated_at']='2026-11-07';assert sets=={k:set(l[k]) for k in sets};dump(path,l)
for name in ['LEDGER_CODEX_NEXUS_INTEGRACAO_ATENCAO_ONBOARDING.md','plans/agent_ops/implementation-report.md']:
    with (ROOT/name).open('a',encoding='utf-8') as s:
        s.write('\n\n## 2026-11-07 — R3: versões, imports e pacotes\n\nQuatro pares instalados qualificados: versões Core alinhadas aceitas; dois pares cruzados recusados com VERSION_INCOMPATIBLE antes de efeitos. 131 módulos Core importados sob guards, nove controles negativos e stdout bruto retido; fronteiras atuais sem violação. Pacotes completos: Nexus690/Connector123/Core165 arquivos, sem recurso-fonte omitido. RG06/07/08 e AC07 verificados para o snapshot Windows atual. Documentação de compatibilidade e proposta Windows vigente atualizadas. Rastreabilidade vinculada sem somar reruns; RG09, AC09/10 e campanhas reais continuam abertos. Revisão tarefa/cenário a tarefa/cenário segue somente leitura. Evidência: `plans/agent_ops/evidence/r3-compatibility-boundaries/milestone.md`.\n')
with (ROOT/'.gitattributes').open('a',encoding='utf-8') as s: s.write('plans/agent_ops/evidence/r3-compatibility-boundaries/** -text -whitespace\n')
print(json.dumps(dict(artifacts=len(manifest),rg_verified=['RG-06','RG-07','RG-08'],ac_verified=['AC-07'])))
