from pathlib import Path
import hashlib,json,shutil
ROOT=Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
OUT=ROOT/'plans/agent_ops/evidence/r3-public-artifact-review'
def dump(p,o): p.write_text(json.dumps(o,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
shutil.copyfile('C:/Users/jpamb/AppData/Local/Temp/r3-public-review-m0zr_900/scan.json',OUT/'scan-after.json')
before=json.loads((OUT/'scan-before.json').read_text(encoding='utf-8'))
after=json.loads((OUT/'scan-after.json').read_text(encoding='utf-8'))
classifications=json.loads((OUT/'classifications.json').read_text(encoding='utf-8'))
allowed={x['literal_sha256'] for x in classifications['findings'] if x['classification'].startswith(('INVALID_','SYNTHETIC_'))}
assert len(after['findings'])==35 and all(x['literal_sha256'] in allowed for x in after['findings'])
changed=[]
for repo,files in before['inventory'].items():
    assert files.keys()==after['inventory'][repo].keys()
    for name,meta in files.items():
        if meta!=after['inventory'][repo][name]: changed.append(repo+':'+name)
assert len(changed)==3,changed
summary='''# R3 — revisão dos artefatos públicos e correção de redação

Revisados 1.822 arquivos públicos rastreados: 1.727 Nexus, 70 Connector e 25 Core. A allowlist contém docs, exemplos, plans/agent_ops e metadados/documentação da raiz. Hashes por arquivo e exclusões binárias estão em scan-before.json/scan-after.json. A revisão não enumera cofres, bancos privados, contas, configurações pessoais ou histórico Git.

As 37 ocorrências iniciais foram classificadas individualmente, sem copiar os valores. Duas exigiram correção: api_key do registro de um operador em evidência UAT de setembro e lane_ticket sintético num traceback histórico PR-06. Foram substituídas por marcadores explícitos. JSON/estrutura XML, identidades, estados, contagens e falhas permanecem preservados. O registro de proveniência PR-06 mantém o hash anterior e documenta o hash corrigido; nenhum resultado foi promovido. corrections.json registra hashes antes/depois e a razão da transformação.

As outras 35 ocorrências são parâmetros de recusa: 32 URLs sintéticas com userinfo, rastreadas aos respectivos testes, e três chaves propositalmente inválidas por alfabeto/tamanho. Não são credenciais de contas. A segunda varredura encontrou somente esses parâmetros; zero novos valores com os padrões de chave Nexus, provedor, GitHub, chave privada ou URL sensível examinados.

Limites: varredura por padrões não comprova ausência universal de segredos, nem inspeciona conteúdo visual de binários. Não houve autenticação, revogação ou consulta da chave UAT histórica; sua validade atual é desconhecida. Commits anteriores não foram reescritos e podem reter os valores anteriores. AC-10 permanece NOT_VERIFIED; a fatia de revisão/correção do snapshot público atual está verificada. Campanhas futuras precisam manter a mesma revisão de artefatos. Não houve mudança de aplicação, wheel ou configuração pessoal.

Validação desta correção: comparação estrutural JSON/XML e contagens originais, mapeamento dos 35 falsos positivos à fonte dos testes, segunda varredura dos mesmos 1.822 arquivos, hashes exatos e checker do ledger fixo. Não se repetiram suites de produto para esta redação documental. Este marco não conclui M1/M2 ou R3.
'''
(OUT/'milestone.md').write_text(summary,encoding='utf-8')
shutil.copyfile(__file__,OUT/'close-review.py')
dump(OUT/'verification.json',dict(files=1822,initial_findings=37,removed_values=2,classified_synthetic_parameters=35,unclassified=0,changed_public_files=changed,product_changed=False,
    current_snapshot_only=True,personal_state_accessed=False,git_history_rewritten=False,credential_revocation_performed=False))
manifest={p.relative_to(OUT).as_posix():dict(sha256=hashlib.sha256(p.read_bytes()).hexdigest(),bytes=p.stat().st_size) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='artifact-manifest.json'}
dump(OUT/'artifact-manifest.json',dict(format='r3-public-artifact-review-v1',files=manifest))
p=ROOT/'plans/agent_ops/ledger.json';l=json.loads(p.read_text(encoding='utf-8'))
prefix='plans/agent_ops/evidence/r3-public-artifact-review/'
ev=[prefix+n for n in ['milestone.md','corrections.json','classifications.json','verification.json','artifact-manifest.json']]
row=l['completion_criteria']['AC-10'];assert row['status']=='NOT_VERIFIED'
row['evidence']=sorted(set(row['evidence']+ev))
row.setdefault('subscopes',{})['current_public_allowlist_review_and_two_historical_redactions']='VERIFIED'
row['remaining']='Current public snapshot reviewed and two raw credential values removed. Historical UAT key validity/revocation and prior Git objects were not checked or modified. Pattern scan does not cover arbitrary secrets or binary visual content; future campaign artifacts remain subject to review.'
l['campaigns']['r3_public_artifact_review']=dict(status='VERIFIED',scope='Current tracked public allowlist only; no universal secret/history or revocation claim',public_files=1822,redacted_values=2,synthetic_parameter_occurrences=35,evidence=ev)
l['history'].append(dict(date='2026-11-07',milestone='PR-10',status='IN_PROGRESS',summary='Reviewed 1822 tracked public files across three repos. Removed one historical UAT API key and one synthetic lane ticket from two retained reports; preserved JSON/XML outcomes and amended original hash provenance. Classified 35 remaining matches as invalid synthetic test parameters. AC-10 remains NOT_VERIFIED: no credential revocation or Git history rewrite, and pattern/binary limits remain explicit. No product or personal-state change.',evidence=ev))
l['updated_at']='2026-11-07';dump(p,l)
for name in ['LEDGER_CODEX_NEXUS_INTEGRACAO_ATENCAO_ONBOARDING.md','plans/agent_ops/implementation-report.md']:
    with (ROOT/name).open('a',encoding='utf-8') as s:
        s.write('\n\n## 2026-11-07 — R3: revisão e redação de artefatos públicos\n\nRevisados 1.822 arquivos públicos dos três repos. Dois valores foram redigidos em relatórios históricos: uma chave UAT e um ticket sintético de fixture. Hashes antes/depois, fonte e falhas originais permanecem documentados; 35 ocorrências restantes são parâmetros inválidos de testes. A segunda varredura confirmou essa classificação. AC-10 permanece aberto: a validade/revogação da chave UAT e commits anteriores não foram alterados ou verificados, e a varredura tem limites declarados. Aplicações/wheels e configurações pessoais inalterados. Evidência: `plans/agent_ops/evidence/r3-public-artifact-review/milestone.md`.\n')
with (ROOT/'.gitattributes').open('a',encoding='utf-8') as s:
    s.write('plans/agent_ops/evidence/r3-public-artifact-review/** -text -whitespace\n')
print(json.dumps(dict(artifacts=len(manifest),public_files=1822,redactions=2,ac10=row['status'])))
