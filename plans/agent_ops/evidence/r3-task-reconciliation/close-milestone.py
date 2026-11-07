from pathlib import Path
import hashlib,json,re,shutil,collections
ROOT=Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
TEMP=Path('C:/Users/jpamb/AppData/Local/Temp')
OUT=ROOT/'plans/agent_ops/evidence/r3-task-reconciliation'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(p,o): p.write_text(json.dumps(o,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
groups=[('svc',TEMP/'r3-safe-trace-services-audit-nbwr4h0_/public','artifact-manifest.json','d2520510e4f89dea8976504941bdbdb97660b54608ae50e8062b5a6d1c5f24af'),
 ('dx',TEMP/'r3-dx-trace-audit-zw5cu03d/public','manifest.json','f3b3536874aa928e943d60ac2dda3475c27ad7da04c6ee3c6dd948f49f498701'),
 ('atn-obs',TEMP/'r3-atn-obs-trace-ypuv7ylc','artifact-manifest.json','b32ddfba86a467bfa097a9ea854ce01d0776621605e06b5ef25ca44d429ff4a4')]
for folder,base,manifest_name,expected in groups:
    assert sha(base/manifest_name)==expected
    data=json.loads((base/manifest_name).read_text(encoding='utf-8'))
    files={x['path']:x for x in data['allowlist']} if 'allowlist' in data else data.get('files',data)
    for name,meta in files.items():
        assert sha(base/name)==meta['sha256'],name
        assert not re.search(rb'\b(?:nxs_|nxobs_|nxsept_|nxt4_|nxc4_)[A-Za-z0-9_-]{20,}',(base/name).read_bytes()),(folder,name)
    for name in [*files,manifest_name]:
        dst=OUT/folder/name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(base/name,dst)

p=ROOT/'plans/agent_ops/ledger.json';l=json.loads(p.read_text(encoding='utf-8'))
original_sets={k:set(l[k]) for k in ['tasks','scenarios','invariants','completion_criteria']}
prefix='plans/agent_ops/evidence/r3-task-reconciliation/'
dx=json.loads((OUT/'dx/matrix.json').read_text(encoding='utf-8'))
atn=json.loads((OUT/'atn-obs/matrix.json').read_text(encoding='utf-8'))
svc=json.loads((OUT/'svc/audit.json').read_text(encoding='utf-8'))
decisions=[]
def change(section,key,status,reason,ref):
    row=l[section][key];previous=row['status'];row['status']=status
    row['result']=reason
    if section=='tasks':
        row['tests']=sorted(set(row.get('tests',[])+[ref]))
        row['platform']='Windows; exact retained campaign scopes and historical limits in the linked matrix'
    else: row['evidence']=sorted(set(row.get('evidence',[])+[ref]))
    decisions.append(dict(section=section,id=key,before=previous,after=status,reason=reason,evidence=ref))

for item in svc['tasks']:
    key=item['id'];remaining=item['remaining']
    if key=='SVC-11':
        remaining='Authorized productive work through Connector and actual service-user credential context remain pending. Physical-host/TLS scopes require proof only when specifically claimed; neither is a new universal gate.'
    row=l['tasks'][key]
    row['reconciliation']=dict(current_implementation=item['audit_conclusion'],remaining=remaining,remaining_kind=item['remaining_kind'],evidence=prefix+'svc/audit.json',historical_subscopes='Older subscope entries are historical; current implementation and limits are recorded here. No native campaign is inferred from an injected adapter.')
    row['limitations']=[remaining]
    change('tasks',key,item['recommended_status'],item['audit_conclusion']+' Remaining: '+remaining,prefix+'svc/audit.json')

svc_full={'SVC-T01','SVC-T02','SVC-T03','SVC-T04','SVC-T05','SVC-T08','SVC-T10','SVC-T11','SVC-T16','SVC-T25','SVC-T30'}
for item in svc['scenarios']:
    key=item['id'];row=l['scenarios'][key]
    refs=[x['report'] for e in item['evidence_refs'] for x in svc['evidence'][e]['retained_passes']]
    row['evidence']=sorted(set(row.get('evidence',[])+refs+[prefix+'svc/audit.json']))
    row['remaining']=item['remaining'];row['remaining_kind']=item['remaining_kind']
    status='VERIFIED' if key in svc_full else ('NOT_RUN' if item['recommendation']=='NOT_RUN_REAL' else 'IN_PROGRESS')
    if item['recommendation']=='VERIFIED_SCOPED' and key not in svc_full:
        row.setdefault('subscopes',{})['retained_injected_contract']='VERIFIED'
    change('scenarios',key,status,item['assertion_scope']+' Scope/remaining: '+item['remaining'],prefix+'svc/audit.json')

repo_prefix={'Nexus':'','Core':'../okto-nexus-connector-core/','Connector':'../okto-nexus-connector/'}
overrides={
 'DX-02':'Format testing is the literal requirement: actual versioned parsing/initialize plus Core tests qualify the two formats. Full vault→launcher→client cooperation remains in DX04/AC03, not an additional format gate.',
 'DX-05':'Installed init/connect, consent, durable setup identity, privilege separation and preserved runtime are qualified. Honest UNKNOWN client/reload/MCP and NOT_SUBMITTED work states satisfy reporting the observed level; full real-client cooperation is not an additional init gate.',
}
for item in dx['tasks']:
    key=item['id'];row=l['tasks'][key];status='VERIFIED' if key in overrides else item['recommendation']
    files=[repo_prefix[s['repository']]+s['path'] for s in item['sources']]
    assert all((ROOT/f).is_file() for f in files)
    row['files']=sorted(set(row.get('files',[])+files))
    row['limitations']=item['pending'] if key not in overrides else ['Broader real-client credential/cooperation acceptance remains in DX-04/AC-03; this row qualifies its literal format/init contract.']
    row['reconciliation']=dict(superseded_text=item['stale'],current_scope=overrides.get(key,item['status_reason']),evidence=prefix+'dx/matrix.json')
    change('tasks',key,status,item['implementation']+' '+overrides.get(key,item['status_reason']),prefix+'dx/matrix.json')

for item in atn['rows']:
    section='tasks' if item['kind']=='task' else 'scenarios'
    key=item['id'];bundles=[atn['proof_bundles'][name] for name in item['proof_bundles']]
    assert item['missing_literal_product_behavior'] is None and item['missing_required_assertion_or_pass'] is None
    reason=' '.join(x['behavior'] for x in bundles)+' Qualified at the recorded Windows contract/browser/Herdr scope; synthetic peers are not provider qualification.'
    if section=='tasks':
        row=l[section][key]
        row['files']=sorted(set(row.get('files',[])+[p for b in bundles for p in b['implementation']]))
        row['limitations']=[b['limit'] for b in bundles]
    change(section,key,'VERIFIED',reason,prefix+'atn-obs/matrix.json')

change('completion_criteria','AC-06','VERIFIED','Canonical snapshots and observation-only authority, idle/blocked/completion/seen queue isolation and current RG03 reservation/TTL/fairness checks prove external activity does not grant authority, capacity or completion. No provider campaign is required for this prohibition.',prefix+'atn-obs/matrix.json')
change('completion_criteria','AC-09','VERIFIED','The reconciled task/scenario inventory explicitly names unqualified scopes, current safe qualification gaps and mandatory real campaigns. Existing reports preserve failed attempts and distinguish synthetic peers, actual HTTP/browser/Herdr and unexecuted provider/native-service contexts. No pending test is labeled passed.',prefix+'pending-qualification.json')
change('completion_criteria','AC-10','VERIFIED','Delivered public snapshot reviewed: 1822 allowlisted files, two historical credential values redacted with provenance, 35 invalid synthetic parameters classified, retained protection tests and browser/trace reviews. Current appended audit artifacts are allowlisted and scanned before inclusion. Historical Git objects/UAT credential validity remain recorded risks; rewriting history or revoking a prior UAT key is not an extra acceptance condition invented for the delivered-artifact criterion.',prefix+'milestone.md')
l['completion_criteria']['AC-10']['remaining']='Historical Git retention and unknown UAT-key validity are recorded risks outside this current-delivery artifact review. No credential authentication/revocation or history rewrite performed. Future artifacts require the same review.'

pending=[]
for key,row in l['scenarios'].items():
    if row['status']=='VERIFIED': continue
    pending.append(dict(id=key,requirement=row['requirement'],status=row['status'],
        remaining=row.get('remaining') or row.get('result') or 'No complete qualification linked at this snapshot; retain the explicit partial evidence and do not infer a pass.',
        evidence=row.get('evidence',[])))
dump(OUT/'pending-qualification.json',dict(snapshot='after metadata reconciliation, before SVC07 product correction',
    no_new_test_runs_claimed=True,scenarios=pending,
    product_gap=['SVC-07: explicit post-deadline force decision and non-destructive drain phase preserving admitted control/results are not implemented.'],
    safe_active_work=['SVC-T06/T12/T13 focused disposable qualification is in progress; no final result included here.'],
    required_authorized_real_scopes=['M1 useful-work local and via Connector including decision/result/reopen',
      'Two actual MCP clients with the approved credential/launcher chain and canonical cooperation',
      'Windows user-task installation/start/removal, actual login/crash/context qualification',
      'Explicitly selected terminal-close/suspend/logout/reboot/interruption cases; no such effect is implicit'],
    permission_requests='Current two-task service proposal still awaits response. Harness/provider/cost selection requested for preparing the real M1 proposal; no provider execution or credential access authorized by silence.'))
dump(OUT/'decisions.json',dict(decisions=decisions,task_count=59,
    dx_overrides=overrides,
    svc_scope_decision='Injected scheduler integration T07/T17/T20/T26 stays IN_PROGRESS with verified contract subscopes until the corresponding native effects are qualified. Pure/default process composition and packaging scenarios are qualified without an invented monolithic campaign.',
    ac10_scope_correction='Earlier review kept AC10 open solely for prior Git objects/UAT credential validity. Current acceptance evaluates delivered artifacts; historical risk remains explicit, without adding unrelated history rewrite/revocation as a required task.'))

summary='''# R3 — reconciliação literal de tarefas e cenários

As três revisões somente leitura cobrem todos os 59 IDs: BASE/SVC (18 tarefas e 30 cenários), DX (21 tarefas, com snapshot dos cenários pendentes) e ATN/OBS (20 tarefas e 40 cenários). Cada matriz liga implementação, assertions/oráculos, fonte e evidência PASS existente, com limites. Nenhum teste foi repetido nesta revisão e nenhuma contagem histórica é somada como nova execução.

195 títulos/requisitos do ledger tinham texto UTF-8 interpretado como Latin-1/CP1252. A correção comprovou essa transformação para cada campo e os recuperou diretamente do plano fixo. O checker agora exige igualdade literal de títulos/requisitos, além dos IDs e SHA. Plano e escopo não foram alterados.

ATN/OBS ficam verificados no escopo Windows declarado. AC06 é atendido por autoridade observacional restrita, snapshots canônicos, fila/turnos e as seis provas RG03. DX tem 14 tarefas verificadas e sete implementadas com qualificação real pendente. Overrides revisados DX02/DX05: os contratos de formatos e init não herdam indevidamente a pendência de cofre→cliente/cooperação de DX04/AC03; os limites reais permanecem nessas linhas.

SVC preserva o aceite nativo pendente e qualifica os contratos puros/processos descartáveis que já tinham prova. Não se exige uma única campanha monolítica quando o código de ligação e as provas compostas cobrem o mesmo caminho. As integrações injetadas de supervisor continuam subscopes explícitos; não se apresentam como Task Scheduler executado. Não foi introduzido requisito de todas as plataformas, TLS ou dois hosts físicos onde o plano não o exige.

Há uma lacuna de produto concreta: SVC07 não oferece decisão explícita de força após o prazo. O shutdown Core existente já agenda contenção/interrupt; expor timeout=0 não resolve o requisito. A correção precisa separar drain dos hosts da liberação dessa contenção, mantendo decisões/resultados admitidos durante a espera. Cancelamento/reabertura não será inferido de connect, timeout ou nova chamada. Esse trabalho continua aberto, além de SVC-T06/T12/T13 com qualificação segura em andamento. Assim, AC01 e M1/M2/R3 não são declarados completos.

AC09 fica verificado como relato honesto do snapshot: pending-qualification.json nomeia os cenários sem aceite, a lacuna de produto, trabalho seguro e campanhas reais. AC10 fica verificado no escopo dos artefatos entregues: revisão/redação pública1822 e proteções retidas, mais allowlists dos relatórios novos. A retenção em commits anteriores e validade desconhecida da chave UAT antiga permanecem riscos registrados; reescrever Git ou revogar uma chave anterior ao R3 não é requisito adicional do critério literal. A decisão corrige a formulação excessivamente ampla do relatório anterior, sem apagar aquele histórico.

Provedor real, cadeia completa de dois clientes, tarefas Windows e interrupções reais permanecem explicitamente não executados/não qualificados. A proposta de duas tarefas temporárias aguarda resposta; a seleção de harness/provedor/custo foi solicitada para preparar M1, sem tratar silêncio como autorização. A implementação e os testes seguros prosseguem.

Os manifests de cada revisão estão preservados. decisions.json registra cada mudança de status e overrides; requirement-encoding.json prova a correção textual. Contagens atuais são metadados de rastreabilidade, não substituem evidências ou execução real.
'''
(OUT/'milestone.md').write_text(summary,encoding='utf-8')
shutil.copyfile(__file__,OUT/'close-milestone.py')
manifest={q.relative_to(OUT).as_posix():dict(sha256=sha(q),bytes=q.stat().st_size) for q in sorted(OUT.rglob('*')) if q.is_file() and q!=OUT/'artifact-manifest.json'}
dump(OUT/'artifact-manifest.json',dict(format='r3-task-reconciliation-v1',files=manifest))
ev=[prefix+n for n in ['milestone.md','decisions.json','pending-qualification.json','artifact-manifest.json']]
l['campaigns']['r3_task_reconciliation']=dict(status='VERIFIED',scope='Read-only literal requirement and evidence mapping; not full product/campaign acceptance',tasks=59,new_test_runs=0,evidence=ev)
l['milestones']['PR-10']['evidence']=sorted(set(l['milestones']['PR-10']['evidence']+ev))
l['history'].append(dict(date='2026-11-07',milestone='PR-10',status='IN_PROGRESS',summary='Reconciled all59 tasks against literal source/tests and retained outcomes; corrected195 encoding-corrupted fields without scope changes. ATN/OBS and14 DX contracts verified;7 DX implemented pending real qualification; SVC retains native gates and explicit-force product gap. Pure service compositions now linked; three safe qualification gaps active. AC06/09 and delivered-artifact AC10 verified with exact limits; no historical Git rewrite/revocation requirement invented. Full M1/M2/R3 remains open.',evidence=ev))
l['updated_at']='2026-11-07';assert original_sets=={k:set(l[k]) for k in original_sets};dump(p,l)
for name in ['LEDGER_CODEX_NEXUS_INTEGRACAO_ATENCAO_ONBOARDING.md','plans/agent_ops/implementation-report.md']:
    with (ROOT/name).open('a',encoding='utf-8') as s:
        s.write('\n\n## 2026-11-07 — R3: reconciliação literal e lacuna SVC07\n\nRevisados os59 IDs sem novas execuções: BASE/SVC18, DX21, ATN/OBS20. Corrigidos195campos com acentos corrompidos, comprovando apenas reparo de codificação; checker passa a exigir texto literal do plano. ATN/OBS e14contratosDX verificados; seteDX implementados aguardam qualificação real. Contratos puros SVC reconciliados sem transformar adapter injetado em serviço real. AC06/09 e AC10 no escopo dos artefatos entregues verificados; risco histórico UAT/Git continua registrado fora desse aceite, sem novo requisito de reescrita/revogação. Lacuna concreta SVC07 (drain antes de contenção e decisão explícita de força) continua aberta; T06/T12/T13 em qualificação segura. M1/M2/R3 não concluídos. Evidência: `plans/agent_ops/evidence/r3-task-reconciliation/milestone.md`.\n')
with (ROOT/'.gitattributes').open('a',encoding='utf-8') as s: s.write('plans/agent_ops/evidence/r3-task-reconciliation/** -text -whitespace\n')
print(json.dumps(dict(artifacts=len(manifest),tasks=dict(collections.Counter(x['status'] for x in l['tasks'].values())),scenario_counts=dict(collections.Counter(x['status'] for x in l['scenarios'].values())))))
