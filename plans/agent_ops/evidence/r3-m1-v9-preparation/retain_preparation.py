from pathlib import Path
import json,hashlib,shutil,zipfile,datetime
REPO=Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
T=Path('C:/Users/jpamb/AppData/Local/Temp')
R=T/'m1-v9-preparation-t4xaqhca';E=REPO/'plans/agent_ops/evidence/r3-m1-v9-preparation'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
proposal_sha='9a7004d1670076fd516311932bb894fbd55e47e2625fb6b3dfd89dc66caed279'
assert sha(R/'draft/m1-codex-campaign-proposal-v9.json')==sha(E/'bundle/m1-codex-campaign-proposal-v9.json')==proposal_sha
P=json.loads((E/'bundle/m1-codex-campaign-proposal-v9.json').read_text())
M=json.loads((E/'bundle/artifact-manifest.json').read_text())
assert len(M['files'])==84
for n,v in M['files'].items():assert sha(E/'bundle'/n)==v['sha256']
expected={}
for module,entry in P['package_pins']['packages'].items():
    assert sha(entry['wheel'])==entry['sha256']
    with zipfile.ZipFile(entry['wheel']) as z:
        for name in z.namelist():
            if name.startswith(module+'/') and not name.endswith('/'):
                expected[str((Path(P['package_pins']['python_prefix'])/'Lib/site-packages'/name).resolve())]=hashlib.sha256(z.read(name)).hexdigest()
assert len(expected)==982
actual={str(Path(e['path']).resolve()):e['sha256'] for e in P['package_pins']['files']}
assert len(actual)==len(P['package_pins']['files'])
for path,digest in expected.items():assert actual[path]==digest,path
extra={p:d for p,d in actual.items() if p not in expected}
assert list(extra)==[str(Path(P['package_pins']['python']).resolve())]
assert sha(next(iter(extra)))==next(iter(extra.values()))
review=T/'m1-v9-final-review-mhpmzv_m/review.json';assert sha(review)=='ab77f64ff1d9f3c04d6f9bcd62dc180aef33f11c13d487babf0b356f38efe617'
shutil.copyfile(review,E/'independent-review.json')
addendum=T/'m1-v9-python-pin-review-47dkl5dh/addendum.json'
assert sha(addendum)=='12a8444a73d7479bf1b8ad87cb45e4fc467a04176aa94acfa08425bfc4ad5d67'
shutil.copyfile(addendum,E/'python-pin-review-addendum.json')
preflight=json.loads((E/'root-preflight.json').read_text());assert preflight['proposal_sha256']==proposal_sha and preflight['status']=='PASS_READ_ONLY_PREPARATION_PREFLIGHT'
root_review={'status':'PREPARED_REVIEWED_AWAITING_NEW_EXPLICIT_APPROVAL','proposal_sha256':proposal_sha,
 'reviewed_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'bundle_manifest_sha256':sha(E/'bundle/artifact-manifest.json'),
 'bundle_payloads_verified':84,'future_product_payload_pins_matched_to_wheels':982,'python_pin_verified':True,
 'nexus_fix_commit':'44c3825445144fa48b5c5ccf6b0d2bd48b21c3b7','installed_product_cases':59,
 'controller_unique_cases':24,'installer_unique_cases':27,'python_pin_regression_cases':1,'entry_denial_cases':12,
 'repeated_cases_not_added':True,'policy':P['controller_preparation']['policy'],'counting':P['counting'],
 'preflight':'27 execution module hashes,3 wheels and native binary hash verified;2 exact tasks absent;port54913 probe released;campaign root absent.',
 'provider_calls':0,'native_cli_calls':0,'service_mutations':0,'product_installation_executed':False,
 'execution_authorized':False,'acceptance_promoted':False,
 'approval_reason':'The authorized v8 excluded additional service cycles. It is closed with its reserved slot and permanent fault preserved. This separate v9 proposes six new reservations and eight explicit lifecycle actions.',
 'limits':['Preparation and synthetic guards are not real M1 qualification.',
 'The exact final proposal needs an actual new user receipt; old approvals and synthetic receipts do not authorize execution.',
 'Readiness observations do not reserve the port/tasks; recheck immediately before effects.',
 'No force,logout,reboot,uncertain replay or old controller reset is authorized.']}
(E/'root-review.json').write_text(json.dumps(root_review,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
shutil.copyfile(Path(__file__),E/'retain_preparation.py')
manifest={'status':root_review['status'],'files':{}}
for p in sorted(E.rglob('*')):
    if p.is_file() and p!=E/'artifact-manifest.json':manifest['files'][p.relative_to(E).as_posix()]={'sha256':sha(p),'bytes':p.stat().st_size}
(E/'artifact-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
lp=REPO/'plans/agent_ops/ledger.json';l=json.loads(lp.read_text(encoding='utf-8'))
l['campaigns']['r3_m1_v9_preparation']={'status':root_review['status'],'proposal_sha256':proposal_sha,
 'historical_reserved_admissions':3,'historical_confirmed_productive_admissions':2,'carry_in_minimum_observed_tokens':45843,
 'proposed_new_reservations_maximum':6,'proposed_cumulative_reservations_maximum':9,
 'proposed_preventive_cumulative_tokens':200000,'retained_operational_tolerance_tokens':700000,
 'proposed_tasks':2,'proposed_explicit_lifecycle_actions':8,'proposed_implicit_scheduler_start_maximum':1,
 'pure_unique_cases':52,'entry_denial_cases':12,'provider_calls':0,'service_mutations':0,
 'product_installation_executed':False,'execution_authorized':False,'acceptance_promoted':False,
 'evidence':['plans/agent_ops/evidence/r3-m1-v9-preparation/root-review.json','plans/agent_ops/evidence/r3-m1-v9-preparation/artifact-manifest.json']}
l['history'].append({'date':'2026-11-07','milestone':'M1 v9 finite successor preparation',
 'status':root_review['status'],'summary':'Qualified GET-recovery wheel and fresh dependency target;51 pure unique cases+1 Python pin regression+12 entry denials;root readonly preflight PASS. Preserve3 historical reservations/45843 tokens. Propose6 new/cumulative9 reservations,200000 preventive/700000 tolerance,2 tasks/8 actions. No execution or acceptance.',
 'evidence':['plans/agent_ops/evidence/r3-m1-v9-preparation/root-review.json']})
l['updated_at']=datetime.datetime.now(datetime.timezone.utc).isoformat();lp.write_text(json.dumps(l,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
with (REPO/'LEDGER_CODEX_NEXUS_INTEGRACAO_ATENCAO_ONBOARDING.md').open('a',encoding='utf-8') as f:f.write('''
## 2026-11-07 — M1 v9 preparada, aguardando autorização

Nova proposta pinada incorpora o wheel Nexus corrigido e qualificado em59 casos
instalados. Controlador preserva3 reservas/45.843 tokens, incluindo o slot v8 sem
inferência confirmada. Propõe6 novas/9 reservas cumulativas, preventiva200mil e
tolerância700mil,2 tarefas temporárias/8 ações explícitas e até1start implícito.

51 casos puros únicos (24controller+27instalador),1 regressão do pin Python e12
recusas de entrada passaram. Candidato anterior sem o pin foi rejeitado/preservado.
Repetições não foram somadas. Novo prefixo tem3.209 dependências e produtos ausentes.
Raiz confirmou27 módulos/3wheels/binário por hash,982 pins futuros contra wheels,
tarefas ausentes,porta54913 disponível e raiz nova inexistente. Não reserva a porta.

Proposta `9a7004d1670076fd516311932bb894fbd55e47e2625fb6b3dfd89dc66caed279`
aguarda recibo novo: v8 excluía ciclos adicionais de serviço. Sem force/logout/
reboot/replay/reset, instalação real ou chamada ao provedor. Nenhum aceite promovido.

Evidência: `plans/agent_ops/evidence/r3-m1-v9-preparation/root-review.json`.
''')
with (REPO/'.gitattributes').open('a',encoding='utf-8') as f:f.write('plans/agent_ops/evidence/r3-m1-v9-preparation/** -text -whitespace\n')
print(json.dumps({'status':root_review['status'],'proposal_sha256':proposal_sha,'evidence_files':len(manifest['files'])}))
