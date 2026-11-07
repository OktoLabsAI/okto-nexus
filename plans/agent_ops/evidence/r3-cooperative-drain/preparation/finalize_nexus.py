from pathlib import Path
from datetime import datetime,timezone
import hashlib
import json
import re
import shutil

root=Path(__file__).parent
repo=Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
evidence=repo/'plans/agent_ops/evidence'
drain=evidence/'r3-cooperative-drain'
proposals=evidence/'r3-campaign-proposals'
invariants=evidence/'r3-invariant-reconciliation'
shutil.copy2(root.parent/'svc07-nexus-readonly-review-4fv5g6l6/review.json',drain/'readonly-review.json')
shutil.copy2(root/'curate_readiness.py',proposals/'curate_readiness.py')
shutil.copy2(__file__,drain/'preparation/finalize_nexus.py')
attrs=repo/'.gitattributes'
with attrs.open('a',encoding='utf-8') as f:
    for folder in (drain,proposals,invariants):
        f.write(folder.relative_to(repo).as_posix()+'/** -text -whitespace\n')

# Narrow public evidence scan: emit only locations/digests, never matching values.
patterns={
 'nexus_credential':rb'\b(?:nxs_|nxobs_|nxsept_|nxt4_|nxc4_)[A-Za-z0-9_-]{20,}',
 'provider_key':rb'\b(?:sk-proj-|sk-ant-|sk-)[A-Za-z0-9_-]{24,}',
 'github_key':rb'\b(?:ghp_|github_pat_)[A-Za-z0-9_]{25,}',
 'private_key':rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
 'url_password':rb'https?://[^\s/:<>"\x27]+:[^\s/@<>"\x27]+@',
}
findings=[]
files=[]
for directory in (drain,proposals,invariants):
    for p in directory.rglob('*'):
        if not p.is_file():continue
        files.append(p.relative_to(repo).as_posix())
        raw=p.read_bytes()
        for kind,pattern in patterns.items():
            for match in re.finditer(pattern,raw):
                findings.append({'path':p.relative_to(repo).as_posix(),'kind':kind,'line':raw[:match.start()].count(b'\n')+1,'sha256':hashlib.sha256(match.group()).hexdigest()})
scan={'files':len(files),'findings':findings,'limits':'Finite pattern scan of new public reports only, not proof of all secret shapes; no personal home or credentials read.'}
(drain/'public-review.json').write_text(json.dumps(scan,indent=2)+'\n')
assert not findings,findings

ledger_path=repo/'plans/agent_ops/ledger.json'
d=json.loads(ledger_path.read_text(encoding='utf-8'))
prefix=drain.relative_to(repo).as_posix()
refs=[prefix+'/milestone.md',prefix+'/qualification.json',prefix+'/artifact-manifest.json']
task=d['tasks']['SVC-07']
task['status']='IMPLEMENTED'
task['result']='Cooperative drain delivered in Core and both hosts. 217 Core,194 Connector and247 Nexus installed unique contract cases pass; Nexus also passes45 isolation/recovery cases. New productive work is fenced, admitted authority/results/ACKs continue, timeout stays pending, explicit force checks current generation and expired drain, and unknown resources retain ownership. Real external shutdown/service/provider campaigns remain open.'
task['limitations']=['Actual registered user-service and external logout/shutdown context remain unqualified; synthetic peers do not qualify real provider work.']
task['subscopes'].update(cooperative_core_installed='VERIFIED',cooperative_connector_installed='VERIFIED',cooperative_nexus_installed='VERIFIED',explicit_generation_force='VERIFIED',admitted_authority_continuation='VERIFIED')
task['reconciliation'].update(current_implementation=task['result'],remaining=task['limitations'][0],remaining_kind='real_campaign',evidence=prefix+'/qualification.json')
task['tests']=sorted(set(task['tests']+refs+['../okto-nexus-connector/docs/evidence/cooperative-drain/milestone.md']))
source_report=json.loads((drain/'source/nexus-source-qualification.json').read_text())
task['files']=sorted(set(task['files']+list(source_report['source_files'])))

# Close the finite startup gap identified by the earlier literal task audit.
boundary='plans/agent_ops/evidence/r3-service-boundaries/'
t=d['tasks']['SVC-02']
t['status']='VERIFIED'
t['tests']=sorted(set(t['tests']+[boundary+'summary.json',boundary+'after/installed/tests.xml']))
t['result']='Canonical identity and OS exclusion contracts plus actual occupied-socket startup are verified in disposable Windows processes: fixed endpoint/database, explicit PORT_IN_USE, foreign listener preserved, no alternative owner. This closes the finite missing case identified in the literal audit.'
t['limitations']=[]
t['reconciliation'].update(remaining='None within the disposable Windows ownership/startup contract.',remaining_kind='none',evidence=boundary+'summary.json')
t=d['tasks']['SVC-04']
t['result']='Readiness and failure-state contracts, including actual startup config/migration/storage failures and interrupted connect observation, are verified. Real provider readiness remains separately pending.'
t['limitations']=['Real provider readiness remains unqualified; service readiness never promises provider work.']
t['reconciliation'].update(remaining=t['limitations'][0],remaining_kind='real_campaign')
t['tests']=sorted(set(t['tests']+[boundary+'summary.json']))
t=d['tasks']['SVC-10']
t['result']='Terminal lifecycle controls and explicit generation-bound force decision are implemented and contract-qualified. Real terminal-independent productive operation remains pending.'
t['limitations']=['Real terminal-independent productive operation remains unqualified.']
t['reconciliation'].update(remaining=t['limitations'][0],remaining_kind='real_campaign')
t['tests']=sorted(set(t['tests']+refs))
s=d['scenarios']['SVC-T21']
s.update(remaining='Actual external logout/shutdown bounded persistence remains unqualified.',remaining_kind='real_external_shutdown',result='Installed CLI/HTTP/Core drain preserves admitted work and does not force on timeout. Explicit force is generation-bound and requires an existing expired drain. Supervisor stop intent precedes containment; actual external logout/shutdown remains pending.')
s['evidence']=sorted(set(s['evidence']+refs))
s=d['scenarios']['RG-09']
s['status']='VERIFIED'
s['result']='Named contract campaigns use temporary homes/workspaces and explicit environment allowlists. The previous RG03/RG05 inherited-environment gap is closed by45 current installed cases. This qualifies these finite campaigns only; future authorized native/provider campaigns need their own isolation and cleanup evidence.'
s['subscopes']['idle_and_selected_recovery_environment_isolation']='VERIFIED'
s['evidence']=sorted(set(s['evidence']+refs+[prefix+'/installed/nexus-installed-fixture-retry/environment.json']))
s=d['scenarios']['RG-05']
s['evidence']=sorted(set(s['evidence']+refs))
s['result']='39 selected current recovery cases pass again under the strict isolated environment, preserving exact IDs and no replay. Selected contract coverage is verified; full real network/service/provider recovery acceptance remains open.'
matrix=json.loads((invariants/'matrix.json').read_text())
for row in matrix['invariants']:
    item=d['invariants'][row['id']]
    item.update(status='VERIFIED',result=row['reason'],scope=matrix['scope'],limitations='Contract/architecture invariant only; no promotion of M1/M2 or real native-service acceptance.')
    item['evidence']=sorted(set(item.get('evidence',[])+['plans/agent_ops/evidence/r3-invariant-reconciliation/matrix.json','plans/agent_ops/evidence/r3-invariant-reconciliation/accepted.json']+(refs if row['id'] in ('INV-06','INV-20','INV-21') else [])))
d['campaigns']['r3_cooperative_drain']={'status':'VERIFIED','scope':'Windows installed contracts with synthetic native peers; real service/provider scopes remain open','nexus_unique_installed':292,'nexus_svc07_unique_installed':247,'connector_unique_installed':194,'core_unique_installed':217,'evidence':refs}
d['campaigns']['m1_codex_real'].update(status='PROPOSAL_READY_AWAITING_BUDGET_CLARIFICATION_AND_AUTHORIZATION',proposal='plans/agent_ops/evidence/r3-campaign-proposals/m1-codex-campaign-proposal.json',build_qualification='Isolated official Codex0.157.0 exact executable fingerprint matches Core qualification; personal0.167.0 unchanged. No provider execution.')
native_path=proposals/'native-service-campaign-proposal.json'
d['campaigns']['windows_temporary_user_tasks'].update(payload_refresh_required=False,snapshot=native_path.relative_to(repo).as_posix(),snapshot_sha256=hashlib.sha256(native_path.read_bytes()).hexdigest(),payload_refresh_reason='Current qualified wheel hashes pinned in revision4; exact two tasks remain absent and no registration performed.')
d['updated_at']=datetime.now(timezone.utc).isoformat()
d['history'].append({'date':'2026-11-07','milestone':'SVC07 cooperative drain and invariant reconciliation','result':'292 unique Nexus installed cases; Core/Connector milestones already pushed.28 invariants reconciled; SVC02 finite gap and RG09 environment gap closed. Real campaigns remain unexecuted.','evidence':refs})
ledger_path.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
note='''
## 2026-11-07 — SVC-07: drenagem cooperativa nos três componentes

Core publicado em `3cdba87` e Connector em `ef8e267`. Nexus qualificado com247
casos únicos de drenagem/autoridade/serviço e45 de isolamento/recuperação:
**292 casos instalados aprovados**. Rodadas fonte e instalada não são somadas.
As15 falhas iniciais instaladas foram de preparação/fixture; seus relatórios
permanecem retidos, seguidos de62 retestes aprovados, sem mudança da wheel.
Drain mantém decisões, leases, resultados e ACKs admitidos; novas admissões
ficam bloqueadas. Timeout permanece pendente e força exige geração atual/prazo
vencido. SVC-07 implementado, com campanhas reais ainda abertas.

Os28 invariantes foram reconciliados como contratos/arquitetura, sem promover
M1/M2. SVC-02 fecha a lacuna de porta ocupada e RG-09 fecha o ambiente herdado
dos45 casos. Propostas atuais usam wheels qualificadas; conta já autenticada
e200 mil tokens definem a proposta M1, mas o teto rígido segue sem garantia
técnica e a opção de monitoramento ainda aguarda resposta. Nenhum serviço
nativo/provedor/credencial real foi executado neste milestone.

Evidências: `plans/agent_ops/evidence/r3-cooperative-drain/milestone.md`,
`plans/agent_ops/evidence/r3-invariant-reconciliation/accepted.json` e
`plans/agent_ops/evidence/r3-campaign-proposals/milestone.md`.
'''
for path in ('LEDGER_CODEX_NEXUS_INTEGRACAO_ATENCAO_ONBOARDING.md','plans/agent_ops/implementation-report.md'):
    with (repo/path).open('a',encoding='utf-8') as f:f.write(note)
print(json.dumps({'public_files':len(files),'public_findings':len(findings),'invariants':28,'task_status':'IMPLEMENTED'}))
