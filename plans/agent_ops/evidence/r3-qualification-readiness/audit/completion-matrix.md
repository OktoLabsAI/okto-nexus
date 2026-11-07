# Auditoria finita de conclusão R3

Snapshot publicado: Nexus `26e6c746d61f98820258ad65fcc69b685e0e2acf`, Connector `fb3fff473ff246adcffa9e91573ac85f7a394170`, Core `5d31784362676e7231b5c612c458a4d8f4b5db4a`.

Plano fixo: `20d0fafdedc793b97a277f5d41355d7d597ff724a77687394215eea3113ba996`. A matriz preserva exatamente 17 critérios e 11 cenários RG; não altera estados do ledger. Nenhum teste, provedor, serviço ou credencial foi executado/acessado.

**Conclusão:** R3 permanece incompleto. Há duas pendências concretas e seguras de empacotamento/qualificação, além de campanhas reais e da reconciliação finita de evidências. Não é correto reduzir tudo a autorização pendente.

- O CI publicado usa Connector `63d99d1644555cb9be2b56ed4b31a0f0f5aabf50128078c33dc3e116c601d919`, enquanto a wheel de renovação qualificada é `a8cf18105fa1cdca0443b6a3be08972d5576f72f3ce07e5a19dd9fc7cd59ae5a`. A correção está atribuída, mas não é declarada concluída aqui.
- O Core declara `mcp>=1.30,<2`; os dois import proofs do browser DX04 registram `mcp==1.29.1`. As observações do browser permanecem válidas em seu ambiente histórico, mas não comprovam resolução válida das dependências. A nova venv deve usar requisitos declarados e `pip check`.
- Progresso paralelo informado pelo root: instalação das wheels exatas e `pip check` passaram; oito casos CI estavam em execução. O relatório novo não foi inspecionado nesta auditoria. A correção permanece pendente apenas de fechamento pelo root, sem alterar retroativamente o snapshot publicado.
- AC-04 está sustentado pelo seu critério literal: decisões canônicas reais no browser, CAS/revisões e ausência de lifecycle paralelo. Peer sintético limita o aceite do harness/provedor, não invalida esse critério da central. RG-10 também possui campanhas reais de browser/backend; nenhuma delas equivale a um rerun global no pacote atual.

## Ordem de fechamento

1. SAFE-PACK: encerrar a correção já atribuída de pin/artefato e resolver dependências em ambiente isolado.
2. SAFE-TRACE e SAFE-PUBLIC-REVIEW: vincular critérios aos relatórios exatos, comparar payloads carregados, conferir docs/skips/allowlist e preservar limites históricos.
3. SAFE-RG e SAFE-COMPAT: somente após mapear o existente, executar os casos conjuntos/pares de versões ainda sem prova exata. Fixtures explícitas permitem esse trabalho sem inferência ou serviço nativo registrado.
4. REAL-M1, REAL-SVC, REAL-MCP, REAL-REMOTE e REAL-RECOVERY: preparar/aplicar apenas os escopos explicitamente autorizados. O plano de duas tarefas temporárias não inclui o aceite completo de login/crash/cofre nem autoriza inferência, logout ou reboot.

## Matriz

A redação integral de cada requisito, todas as lacunas e o critério de saída de cada campanha estão no JSON. Evidência histórica não é somada nem apresentada como nova execução.

| ID | Escopo comprovado / limite restante | Próximo fechamento |
|---|---|---|
| AC-01 (NOT_VERIFIED) | Implementation/reuse and installed tests are recorded by milestone across SVC/DX/ATN/OBS; latest guide, remote bootstrap and renewal close several old implementation gaps. **Falta:** No criterion-level closure mapping for every mandatory task at the selected published payload; an empty AC evidence list is not proof that implementation is absent. [ledger_reconciliation, guide, bootstrap] | SAFE-PACK, SAFE-TRACE |
| AC-02 (NOT_VERIFIED) | OBS is optional and independent; browser/HTTP/Core-dispatch fixtures show OBS/attention coexist without canonical writes. Individual SVC, DX and ATN contracts have installed evidence. **Falta:** One explicit combined closure record over the final coordinated package; prerequisite real M1/M2 gates remain open. [herdr, external_attention, correlation] | SAFE-PACK, SAFE-TRACE, SAFE-RG, REAL-M1, REAL-SVC, REAL-MCP |
| AC-03 (NOT_VERIFIED) | Claude Code 2.1.317 and Codex 0.166.0 parsed generated configs and performed authenticated initialize/list against a synthetic responder in isolated protocol modes. **Falta:** Two actual clients participating/cooperating with canonical Nexus through the complete approved credential chain; responder and identity-only fixtures do not establish this. [participant_contract, participant_launch, cooperation] | REAL-MCP |
| AC-04 (VERIFIED) | Real browser and installed HTTP/SQLite exercised canonical approval, question and handoff decisions; stale generic revision returned 409 and canonical handoff verdict reached COMPLETED. **Falta:** No substantive missing evidence for the literal central-action/lifecycle criterion was found. Historical package evidence must not be relabeled as a full current-wheel rerun. [attention_ui, attention_browser_root, attention_browser_final] | SAFE-TRACE |
| AC-05 (NOT_VERIFIED) | Canonical message/handoff request IDs, fixed replay windows, lost replies, failed checkpoint writes and actual process-death recovery are qualified. **Falta:** Explicit all-new-path/restart inventory and exact report mapping at the final artifact; no blanket exactly-once claim outside the documented receipt windows. [coordination, cooperation, bootstrap] | SAFE-PACK, SAFE-TRACE, SAFE-RG |
| AC-06 (NOT_VERIFIED) | External reports project only watch/inspection; real HTTP/SQLite/Core dispatch tests show done/seen do not release the queued turn. **Falta:** Explicit mapping covering every priority/fairness/eligibility/reservation assertion in RG-03; preserve the separation when deriving current joint acceptance. [observations, herdr, external_attention] | SAFE-TRACE, SAFE-RG |
| AC-07 (NOT_VERIFIED) | Prior Core pure-import audit recorded zero network/process/thread effects and zero non-code reads; installed boundaries and noneditable payload proofs exist. **Falta:** Published CI manifest still pins Connector wheel 63d99d16... instead of renewal a8cf1810.... [participant_import, renewal_package, guide_package] | SAFE-PACK, SAFE-TRACE |
| AC-08 (NOT_VERIFIED) | Milestones document canonical CLI, receipts, schemas, finite limits, rollback and narrower qualification; published DX04 guide generates public commands without setup effects. **Falta:** Final help/schema/doc comparison spanning the current three-package set and removal of misleading aggregate conclusions from superseded historical limitations. [guide, participant_docs, coordination_docs] | SAFE-TRACE, SAFE-COMPAT |
| AC-09 (NOT_VERIFIED) | Closed reports preserve initial failures, overlaps, named skips and synthetic-versus-real limits; real Herdr, real HTTP/browser and native client protocol modes are explicitly distinguished. **Falta:** Final single inventory of all NOT_RUN cases and environmental/authorization causes, including new package/dependency qualification limits; no execution is required merely to document these honestly. [guide, herdr, cooperation] | SAFE-TRACE, SAFE-PUBLIC-REVIEW |
| AC-10 (NOT_VERIFIED) | Metadata-only checkpoints/exports, protected key input and allowlisted evidence collection exclude private bearer/DB files; retained synthetic secret redactions are documented. **Falta:** One final allowlisted public-artifact/export/log/example/URL review tied to hashes; this audit does not claim an exhaustive or personal-machine secret scan. [bootstrap, renewal, herdr] | SAFE-PUBLIC-REVIEW, SAFE-TRACE |
| AC-11 (NOT_VERIFIED) | Terminal send/watch/question/decision/result/recovery, project identity/preset and Connector setup/renewal have actual HTTP/SQLite/IPC transport evidence with synthetic native/provider behavior. **Falta:** Actual useful native-harness/provider cycle locally and via Connector, including decision, result, no mandatory dashboard/keep-alive terminal and re-entry to the same work. [terminal_work, identity, policy] | SAFE-PACK, REAL-M1, REAL-SVC, REAL-REMOTE |
| AC-12 (NOT_VERIFIED) | Real contender processes and installed three-concurrent-starter campaigns prove one owner, late-child rejection, reuse, restart and canonical drain in both hosts. **Falta:** Final artifact carry-forward and exact remote/no-double-supervisor case mapping; actual registered-supervisor coexistence is part of REAL-SVC, not proven by injected task effects. [locks, launch_recovery, passive_connector] | SAFE-PACK, SAFE-TRACE, REAL-SVC |
| AC-13 (NOT_VERIFIED) | Windows task definition/ownership/control contracts, validate-only XML and injected native effects are implemented; detached processes are real. **Falta:** Actual native install, login start, stop, supervised crash/recovery and removal with real execution-context credential access. The pending two-task plan alone explicitly excludes login/logout/crash/credential acceptance. [native_campaign, launch_recovery, upgrade] | REAL-SVC |
| AC-14 (NOT_VERIFIED) | Detached restart, receipt/process-death recovery, live Herdr disconnect/replacement and remote epoch/grant uncertainty contracts have narrower evidence. **Falta:** Actual service/native-work restart, approved suspend/resume and network interruption with authority/ownership/uncertainty checked; loopback and synthetic peers do not establish real provider continuity. [launch_recovery, coordination, herdr] | SAFE-TRACE, SAFE-RG, REAL-RECOVERY |
| AC-15 (NOT_VERIFIED) | Installed real CLI/detached lifecycle and passive status/logs/default doctor preserve absent state, do not create vaults/start work, and expose uncertainty; upgrade/drain/foreground paths have historical evidence. **Falta:** Current coordinated artifact mapping of the control/passivity cases; registered-task control qualification remains within AC-13 and must not be silently inferred. [passive_connector, doctor, launch_recovery] | SAFE-PACK, SAFE-TRACE |
| AC-16 (NOT_VERIFIED) | Persistent reviewed identity, generalist role, scoped coordination permissions, finite grants and operator-only decisions are implemented and tested; remote Finish commits the reviewed configuration. **Falta:** Actual effective native harness context/tools/permissions and useful scoped collaboration in the default local/remote flow, without admin authority or self-approval. [identity, policy, remote_preset] | REAL-M1, REAL-MCP |
| AC-17 (NOT_VERIFIED) | Optional preset evolution retains custom choices; ordinary reconnect does not reapply defaults; remote completed reuse after explicit key rotation preserves bootstrap/Finish/configuration. **Falta:** Final cross-artifact carry-forward and actual continued useful native terminal cycle after reconnect/update/interface reopen; historical contracts do not close M1. [preset_evolution, dashboard, guide] | SAFE-PACK, SAFE-TRACE, REAL-M1, REAL-RECOVERY |
| RG-01 (NOT_RUN) | Canonical MCP coordination, identity-only peer replies and managed-runtime setup each have isolated transport/persistence evidence. **Falta:** One combined two-MCP-participant plus managed-runtime workspace scenario proving unique identities; no exact authoritative retained run was mapped here. [cooperation, coordination, bootstrap] | SAFE-PACK, SAFE-TRACE, SAFE-RG |
| RG-02 (NOT_RUN) | Canonical claim/admission and coordination tests cover related concurrency; a default-start concurrent-claim test exists, but is not evidence of this exact mixed-channel broadcast race. **Falta:** Exact simultaneous MCP/runtime broadcast claim with one committed winner, no duplicate lease/reservation/result and retained loser refusal. [coordination, cooperation] | SAFE-TRACE, SAFE-RG |
| RG-03 (NOT_RUN) | Installed external-observation isolation cases for OBS on/off prove done/seen do not release a turn or wake queued work; canonical row fingerprints remain unchanged in OBS browser/load campaigns. **Falta:** Exact idle assertions for priority, fairness, eligibility and claim reservations over the relevant scheduler paths; generic no-work-completion is narrower. [external_attention, correlation, correlation_installed] | SAFE-TRACE, SAFE-RG |
| RG-04 (NOT_RUN) | Prior one-shot claim/admission and configuration-mode validation cases are retained; canonical isolation behavior is reused. **Falta:** A retained behavior matrix exercising shared/per_sender/per_sender_session/one_shot together with the new paths; configuration parser acceptance alone is insufficient. [coordination, terminal_work, remote_preset] | SAFE-TRACE, SAFE-RG |
| RG-05 (NOT_RUN) | Real process death/console recovery, bootstrap response loss, authorization submitted uncertainty and observer reconnection preserve original metadata and reject replay. **Falta:** One finite inventory mapping every new productive entry/recovery path and its fault boundary to an existing retained result; do not infer all paths from one receipt suite. [coordination, cooperation, bootstrap] | SAFE-PACK, SAFE-TRACE, SAFE-RG |
| RG-06 (IN_PROGRESS) | Core pure import/render audit recorded zero sockets/process/thread effects and zero non-code reads; installed tests enforce domain/application import boundaries. **Falta:** Tie these checks and prohibited application-dependency scans to the corrected final three-package environment, including valid declared dependencies. [participant_import, participant_contract, correlation_installed] | SAFE-PACK, SAFE-TRACE |
| RG-07 (NOT_RUN) | CLI coordination documents refusal of absent receipt contract; service lifecycle diagnoses incompatibility; native work retains uncertainty for missing correlation. **Falta:** Explicit supported old/new pair table and evidence for both directions; additive API statements do not constitute a complete version-pair campaign. [coordination_docs, service_docs, terminal_work] | SAFE-COMPAT |
| RG-08 (IN_PROGRESS) | Latest published Nexus guide wheel has 690 raw files equal across source/staging/wheel/installation, including UI; prior coordinated wheels include migrations/resources and use noneditable imports. **Falta:** CI Connector pin is stale relative to latest published source; final coordinated dependency-solve/import/resource proof is pending. [guide_package, renewal_package, guide_import_agents] | SAFE-PACK, SAFE-TRACE |
| RG-09 (NOT_RUN) | Published campaigns use disposable homes/workspaces, synthetic fixtures and explicit public allowlists; real Herdr/browser servers have recorded canonical cleanup. **Falta:** Final campaign inventory/allowlist review and the corresponding isolation/cleanup evidence for future authorized campaigns. [guide, bootstrap, renewal] | SAFE-PUBLIC-REVIEW, SAFE-TRACE |
| RG-10 (VERIFIED) | Actual Chrome/Playwright interaction against installed HTTP/SQLite exists for project introduction, attention decisions, external OBS/correlation and the latest published DX04 guide. **Falta:** No missing browser interaction evidence was identified for those delivered UI surfaces. Dependency-invalid DX04 environment cannot serve as a reproducible dependency solve; it does not erase actual browser observations. [dashboard, attention_ui, attention_browser_final] | SAFE-PACK, SAFE-TRACE |
| RG-11 (NOT_RUN) | Canonical coordination/delivery and managed-runtime origins have related tests; no complete exact same-agent MCP-plus-runtime delivery exclusion run was mapped here. **Falta:** One logical delivery for the same identity with MCP and managed runtime concurrently eligible, including loser/consumption state and no channel fan-out. [coordination, cooperation, renewal_package] | SAFE-PACK, SAFE-TRACE, SAFE-RG |

## Evidências citadas

Caminhos relativos à raiz Nexus; o JSON registra SHA-256 e tamanho de cada arquivo. Os artefatos originais não foram alterados.

- `locks`: `plans/agent_ops/evidence/pr01-locks.md`
- `launch_recovery`: `plans/agent_ops/evidence/pr02-launch-recovery.md`
- `upgrade`: `plans/agent_ops/evidence/pr02-upgrade.md`
- `passive_connector`: `plans/agent_ops/evidence/pr02-connector-passive.md`
- `doctor`: `plans/agent_ops/evidence/pr03-project-doctor.md`
- `terminal_work`: `plans/agent_ops/evidence/pr03-terminal-work.md`
- `identity`: `plans/agent_ops/evidence/pr03-terminal-identity.md`
- `policy`: `plans/agent_ops/evidence/pr03-terminal-policy.md`
- `remote_preset`: `plans/agent_ops/evidence/pr03-remote-preset.md`
- `preset_evolution`: `plans/agent_ops/evidence/pr03-preset-evolution.md`
- `dashboard`: `plans/agent_ops/evidence/pr03-project-dashboard.md`
- `participant_contract`: `plans/agent_ops/evidence/pr04-participant-contract.md`
- `participant_import`: `plans/agent_ops/evidence/pr04-participant-contract-import.json`
- `participant_launch`: `plans/agent_ops/evidence/pr04-participant-launch.md`
- `participant_removal`: `plans/agent_ops/evidence/pr04-participant-removal.md`
- `cooperation`: `plans/agent_ops/evidence/pr04-cooperation.md`
- `coordination`: `plans/agent_ops/evidence/pr05-coordination-cli.md`
- `attention_backend`: `plans/agent_ops/evidence/pr06-attention.md`
- `attention_ui`: `plans/agent_ops/evidence/pr07-attention-ui.md`
- `attention_browser_root`: `plans/agent_ops/evidence/pr07-attention-ui/root-results.json`
- `attention_browser_final`: `plans/agent_ops/evidence/pr07-attention-ui/final-results.json`
- `attention_installed`: `plans/agent_ops/evidence/pr07-attention-ui-contracts-installed.xml`
- `observations`: `plans/agent_ops/evidence/pr08-observations.md`
- `herdr`: `plans/agent_ops/evidence/pr09-herdr.md`
- `external_attention`: `plans/agent_ops/evidence/pr10-external.md`
- `correlation`: `plans/agent_ops/evidence/pr10-correlation.md`
- `correlation_installed`: `plans/agent_ops/evidence/pr10-correlation/candidate-v2/installed.xml`
- `ledger_reconciliation`: `plans/agent_ops/evidence/pr10-ledger-reconciliation.md`
- `bootstrap`: `plans/agent_ops/evidence/pr03-remote-bootstrap.md`
- `renewal`: `plans/agent_ops/evidence/pr03-remote-renewal.md`
- `renewal_package`: `plans/agent_ops/evidence/pr03-remote-renewal/candidate-v2/package-proof.json`
- `guide`: `plans/agent_ops/evidence/pr04-participant-guide/milestone.md`
- `guide_package`: `plans/agent_ops/evidence/pr04-participant-guide/installed/candidate-v1/package-proof.json`
- `guide_import_agents`: `plans/agent_ops/evidence/pr04-participant-guide/installed/servers/agents/import-proof.json`
- `guide_import_onboarding`: `plans/agent_ops/evidence/pr04-participant-guide/installed/servers/onboarding/import-proof.json`
- `native_campaign`: `plans/agent_ops/campaigns/windows-user-service.md`
- `service_docs`: `docs/service-lifecycle.md`
- `coordination_docs`: `docs/terminal-coordination.md`
- `participant_docs`: `docs/terminal-participant.md`

## Limites da auditoria

Não executa regressão, não prova ausência universal de defeitos e não promove tarefas. Um caso com nome semelhante não foi tratado como prova de RG-02/04/11. A leitura encontrou evidências mais amplas do que alguns campos AC/RG do ledger, mas essa reconciliação exige referência exata, não atualização automática.

Não propõe adoção automática de definições de serviço alteradas, novas plataformas, SLOs ou APIs. TLS/dois hosts são escopos de implantação a qualificar quando declarados, não exigências inventadas para toda instalação válida.

Os resultados futuros dos trabalhos paralelos devem produzir uma nova revisão desta matriz; este snapshot publicado e suas pendências não devem ser sobrescritos retroativamente.
