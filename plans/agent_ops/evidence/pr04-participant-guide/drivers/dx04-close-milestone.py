import copy, hashlib, json, pathlib, re, shutil

root=pathlib.Path(r'D:/Projetos/Techridy/okto_labs_okto_nexus')
temp=pathlib.Path(r'C:/Users/jpamb/AppData/Local/Temp')
draft=temp/'pr04-participant-guide-closure-y14puil7'
installed=temp/'dx04-mcp-guide-installed-sk13m28a/public-installed'
browser=root/'output/playwright/dx04-participant-guide'
rel='plans/agent_ops/evidence/pr04-participant-guide'
dest=root/rel
assert not dest.exists(), 'Milestone closure is intentionally one-shot'
plan=hashlib.sha256((root/'PLANO_CODEX_NEXUS_INTEGRACAO_ATENCAO_ONBOARDING.md').read_text(encoding='utf-8').encode()).hexdigest()
assert plan=='20d0fafdedc793b97a277f5d41355d7d597ff724a77687394215eea3113ba996'
def read(p): return json.loads(p.read_text(encoding='utf-8'))
def write(p,d): p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
package=read(installed/'candidate-v1/package-proof.json')
assert package['exact_source_stage_wheel_installed'] and package['file_count']==690
for name,digest in package['files'].items():
    assert hashlib.sha256((root/'src/okto_nexus'/name).read_bytes()).hexdigest()==digest, name
for name in ['agents','onboarding']:
    c=read(installed/'servers'/name/'table-comparison.json')
    s=read(installed/'servers'/name/'shutdown.json')
    assert c['checked_comparisons']==34 and c['canonical_unchanged'] and c['raw_agent_unchanged'] and not c['changed']
    assert s['process_exited'] and s['canonical_result']['shutdown']['state']=='DRAINED'
br=read(browser/'browser-report.json')
assert br['check_count']==22 and all(c['status']=='PASS' for c in br['checks'])
shutil.copytree(draft/'staged'/rel,dest)
shutil.copytree(installed,dest/'installed')
shutil.copytree(browser,dest/'browser')
(dest/'drivers').mkdir()
for p in [temp/'dx04-browser-run.py',temp/'dx04-browser-report.py',*sorted(temp.glob('dx04-browser-batch*.json')),temp/'dx04-browser-close.json',pathlib.Path(__file__)]:
    shutil.copyfile(p,dest/'drivers'/p.name)

report=read(dest/'reports.json')
report['status']='VERIFIED_DECLARED_WINDOWS_DASHBOARD_SCOPE'
report['platform']='Windows; installed Nexus wheel, real loopback HTTP and Chromium through Playwright CLI'
report['installed_package']=dict(status='VERIFIED',wheel_sha256=package['wheel_sha256'],core_wheel_sha256=package['core_sha256'],
    file_count=690,source_stage_wheel_install_match=True,canonical_bundle='assets/index-Baw-pvQn.js',
    canonical_bundle_sha256='15d170828f24b24417570aa0bf13852d7efe0c9efe45a9bd80d966ebcf4ece2b',
    evidence=['installed/candidate-v1/package-proof.json','installed/servers/agents/static-http-proof.json','installed/servers/onboarding/static-http-proof.json'])
report['installed_browser']=dict(status='VERIFIED_DECLARED_SCOPE',reports='browser/browser-report.json',
    checkpoints=22,command_records=59,command_exit_failures={'08-public-command-assert':1},
    failure_classification='QA selector assumed explicit role=dialog; corrected to native dialog; retained attempts and misleading fields explained in browser-report.',
    identity_runtime_preservation='34 comparisons per Server fixture, all unchanged including raw agents; 33 tables plus separate credential projection',
    empty_server=dict(agents=1,workspaces=0),seeded_server=dict(agents=3,workspaces=2),
    network=br['network'],only_public_guidance_captured=True,service_browser_cleanup='Named QA browser closed; both Server instances canonically DRAINED and PIDs exited',
    evidence=['browser/browser-report.json','browser/60-close-browser.json','installed/servers/agents/table-comparison.json','installed/servers/onboarding/table-comparison.json','installed/servers/agents/shutdown.json','installed/servers/onboarding/shutdown.json'])
report['limitations'][1]='Installed candidate-v1 is verified with the canonical checkout bundle. The historical isolated bundle is not byte-identical; both frontend suite runs overlap.'
report['publication_scope']='Nexus feature/v0.3.3 only. Connector/Core unchanged. No registry publication or merge.'
write(dest/'reports.json',report)
summary=('Dashboard guidance now uses the existing participant CLI for a selected identity/workspace, preserving the public origin and producing no secret-bearing command or extra browser approval gate. '
         'The 138 frontend cases and typecheck/build passed. The installed 690-file Nexus wheel served both real loopback browser fixtures; 22 observed checkpoints passed, with 34 unchanged DB comparisons per fixture and canonical shutdown. '
         'The initial native-dialog selector error was corrected and retained. No real client/vault/provider/native-service or productive M1/M2/full R3 qualification is claimed.')
milestone='''# PR-04 — public participant guidance in the dashboard

Status: verified for the Windows dashboard scope below. Full PR-04 and R3 remain IN_PROGRESS.

The existing-agent action and onboarding now share a public guide for the existing participant CLI. Agent/workspace/profile/client/origin/terminal selections produce init review/apply, supported foreground launch review/apply, passive doctor and optional authenticated MCP doctor commands. Selected workspace is prefilled; All workspaces requires an explicit ID. HTTPS and port are preserved; invalid origins yield no command. Generic clients receive manual guidance without a launch command. Dedicated one-shot key delivery remains separate. Copying or editing this guide performs no setup effect.

Qualification: 138 frontend cases, including 12 guide cases replacing four legacy snippet cases, passed in isolation and the checkout. These runs overlap. Typecheck and Vite build passed; the existing large-chunk warning remains. The root build differs from the isolated artifact by three pre-existing class-whitespace CR escapes (six bytes); root-validation.json records the exact comparison. The canonical index-Baw-pvQn.js was packaged and served.

The noneditable Nexus0.3.3 wheel SHA-256 is `9b18dc0c69673bb730198ca461f2464c8ee4ae3fdc1226f22ffcb8140783412f`. All690 package files match source/staging/wheel/installation. Core0.0.14 is the unchanged vendored wheel. Both Servers ran through their real serve lifecycle with empty discovery and harness/embedding disabled in isolated temporary homes. No persistent service or provider was started.

Playwright CLI observed22 checkpoints over two real HTTP fixtures: selected/read-only identity, required/prefilled workspace, Claude/Codex/generic steps, HTTPS port and invalid HTTP, clipboard success and injected refusal, Escape/focus restoration, keyboard containment, empty-Server onboarding, and390px light/dark layouts. Screenshots were visually reviewed. Console messages were zero on both pages. Recorded request lists contained346 and49 GETs respectively, with successful static requests omitted. The empty fixture stayed at one reserved operator/zero workspaces; the seeded fixture at three agents/two workspaces. All34 comparisons per fixture (33 tables plus credential projection) remained equal, including raw agent hashes; normalization was not needed to obtain equality. No grants, authorization receipts, Finish records or bindings appeared.

Historical QA errors are retained: an early click was intercepted by the normal metrics opt-in until it was explicitly closed; an evaluation incorrectly searched an explicit role attribute for a native dialog and was corrected. Two custom request-monitor attempts supplied no serialized result and are not proof. Browser-report.json identifies those records. No product correction or rebuild was needed during browser validation. The named browser closed; both Servers reached DRAINED and their owned PIDs exited.

This milestone executes no generated terminal command, creates no client configuration and accesses no real vault or provider. Public manual IDs entered in empty onboarding are illustrative, not authenticated identities. Origin validation is a frontend contract; TLS/redirects were not retested. DX-02 actual_client_credential_resolution and authenticated_mcp_participation remain NOT_RUN for the broad real-vault-to-client chain; earlier fixture environment/native initialize evidence is narrower. Full native-service lifecycle, actual-client cooperation, productive M1/M2 and joint R3 acceptance remain open. Connector/Core did not change.

Evidence: [reports](reports.json), [browser report](browser/browser-report.json), [package proof](installed/candidate-v1/package-proof.json), [artifact manifest](artifact-manifest.json). Usage: [participant CLI](../../../../docs/terminal-participant.md).
'''
# Keep prose spacing human-readable rather than the compressed preparation notation.
for a,b in [('Nexus0.3.3','Nexus 0.3.3'),('All690','All 690'),('Core0.0.14','Core 0.0.14'),('observed22','observed 22'),('and390px','and 390 px'),('contained346 and49','contained 346 and 49'),('All34','All 34')]: milestone=milestone.replace(a,b)
(dest/'milestone.md').write_text(milestone,encoding='utf-8')

ledgerpath=root/'plans/agent_ops/ledger.json'
ledger=read(ledgerpath); before=copy.deepcopy(ledger)
proposal=read(draft/'ledger-closure-draft.json')
ev=[rel+'/milestone.md',rel+'/reports.json',rel+'/artifact-manifest.json',rel+'/browser/browser-report.json',rel+'/installed/candidate-v1/package-proof.json']
for item in proposal['proposed_subscope_additions']:
    target=ledger[item['section']][item['id']]
    assert target['status']==item['preserve_status']
    target.setdefault('subscopes',{})[item['subscope']]='VERIFIED'
    target['evidence']=sorted(set(target.get('evidence',[])+ev))
    target['result']=(target.get('result','')+' '+summary).strip()
    if item['section']=='tasks':
        target['files']=sorted(set(target.get('files',[])+['frontend/src/participantGuide.ts','frontend/src/components/ParticipantGuide.tsx','frontend/src/components/onboarding/OnboardingModal.tsx','frontend/src/views/AgentsView.tsx','docs/terminal-participant.md']))
        target['tests']=sorted(set(target.get('tests',[])+['frontend/tests/participantGuide.test.mjs','frontend/tests/mcpSnippet.test.mjs']))
ledger['milestones']['PR-04']['evidence']=sorted(set(ledger['milestones']['PR-04']['evidence']+ev))
ledger['campaigns']['pr04_dashboard_participant_guide']=dict(status='VERIFIED',scope='Windows installed dashboard public guidance only',frontend_unique_tests=138,browser_checkpoints=22,db_comparisons_per_fixture=34,wheel_sha256=package['wheel_sha256'],evidence=ev)
ledger['history'].append(dict(date='2026-11-07',milestone='PR-04',status='IN_PROGRESS',summary=summary,evidence=ev))
ledger['updated_at']='2026-11-07'
for section in ['tasks','scenarios','invariants','completion_criteria','milestones']:
    assert set(ledger[section])==set(before[section])
    assert all(ledger[section][k]['status']==before[section][k]['status'] for k in before[section])
assert ledger['tasks']['DX-02']==before['tasks']['DX-02']
assert ledger['status']==before['status']=='IN_PROGRESS'
write(ledgerpath,ledger)
rootmd=root/'LEDGER_CODEX_NEXUS_INTEGRACAO_ATENCAO_ONBOARDING.md'
with rootmd.open('a',encoding='utf-8',newline='\n') as f:
    f.write('\n## 2026-11-07 — Guia público de participante no dashboard\n\n')
    f.write('Onboarding e agente existente agora compartilham comandos públicos de review/apply/launch/doctor, com origem e workspace explícitos. Snippets que embutiam a chave foram removidos; a entrega one-shot permanece separada. Copiar o guia não cria identidade, gira credencial ou altera runtime.\n\n')
    f.write('Passaram 138 testes de frontend e typecheck/build; 22 checkpoints no navegador usaram o wheel instalado com 690 arquivos conferidos. Nos dois Servers, as 34 comparações de estado permaneceram iguais, inclusive hashes brutos de agentes. As requisições capturadas foram GET; console sem erros/avisos. Layout390px, tema escuro, clipboard, foco e onboarding vazio foram conferidos. Browser encerrado e ambos Servers DRAINED com PIDs finalizados.\n\n'.replace('Layout390px','Layout de 390 px'))
    f.write('Somente subescopos de DX-03/04/05/12 e DX-T01/03/09/11/35 foram verificados. Os status globais e DX-02 cofre real→cliente permanecem iguais; M1/M2/R3 seguem abertos. Connector/Core sem alterações. [Evidências e limites]('+rel+'/milestone.md).\n')
with (root/'plans/agent_ops/implementation-report.md').open('a',encoding='utf-8',newline='\n') as f:
    f.write('\n## PR-04 dashboard participant guide — 2026-11-07\n\n'+summary+' See [evidence](evidence/pr04-participant-guide/milestone.md).\n')
attrs=root/'.gitattributes'
rule='plans/agent_ops/evidence/pr04-participant-guide/** -text -whitespace'
if rule not in attrs.read_text(encoding='utf-8'):
    with attrs.open('a',encoding='utf-8',newline='\n') as f: f.write('# Public participant-guide evidence retains original artifact bytes.\n'+rule+'\n')
artifacts=[]
for p in sorted(dest.rglob('*')):
    if not p.is_file() or p==dest/'artifact-manifest.json': continue
    data=p.read_bytes()
    assert not re.search(rb'\b(?:nxs_|nxobs_|nxsept_|nxt4_|nxc4_)[A-Za-z0-9_-]{20,}\b',data),p
    artifacts.append(dict(path=p.relative_to(dest).as_posix(),bytes=len(data),sha256=hashlib.sha256(data).hexdigest()))
aggregate=hashlib.sha256(json.dumps(artifacts,sort_keys=True,separators=(',',':')).encode()).hexdigest()
write(dest/'artifact-manifest.json',dict(schema_version=1,scope='Closed public participant-guide Windows dashboard milestone',plan_sha256=plan,artifact_count=len(artifacts),aggregate_sha256=aggregate,artifacts=artifacts))
print(json.dumps(dict(evidence=rel,artifacts=len(artifacts),aggregate_sha256=aggregate,frontend=138,browser_checkpoints=22,all_global_statuses_preserved=True),indent=2))
