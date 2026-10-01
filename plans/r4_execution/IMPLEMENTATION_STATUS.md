 # Execução R4 — estado verificado em 2026-10-01

## Running native tool authority and three real Connector providers - October 1, 2026

Connector e2012a3 preserves full installation qualification for every new runtime and revalidates running native actions against their original selection, physical identities, current configuration and Core lease. Installed regressions passed 263 Connector and 33 Nexus cases; 60 directed source cases passed. With Nexus test dfb2b1a, Pi, Codex and Claude all passed through public CLI subprocesses and actual HTTP/WSS to a separate Server process. All completed governed handoffs, renewed leases, successful turn/close receipts, normal Server/daemon shutdown and campaign credential removal; Codex and Claude used three explicit decisions each. Pi's retained diagnostic had measured roughly 26-second bridge calls caused by repeated full qualification around metadata. The running-action correction preserves the existing 10-second native ingress deadline and all launch qualification. The earlier event-loss exception remains unidentified. [Evidence index](test_runs_20261001_running_launch.json), [implementation](M09_RUNNING_TOOL_AUTHORITY.md). Same Core 9c77871 / 0.2.44 and Nexus 68c6e0b product wheel. Direct embedded verification of this Core is next, followed by the existing session reuse/observation/retention backlog. No milestone or release gate closes.

## Core identity read allocation and real CLI processes - October 1, 2026

Core 9c77871 / 0.2.44 bounds counted file reads to remaining expected bytes plus a sentinel, preserving the complete Pi build identity, growth detection and byte budgets. Nexus 68c6e0b and Connector 2390f84 adopt the same wheel. Installed verification: Core 92, Connector 252 and Nexus 33 tests passed; Nexus lock check and an isolated frozen offline install passed. Real Codex and Claude journeys passed with actual CLI subprocesses, renewed leases, three decisions each, completed handoffs, successful turn/close receipts and credential cleanup. Pi opened but remains failed: the final uninstrumented repetition recorded native event observation loss. One response-instrumented Pi pass is diagnostic only; earlier event-loss and uncertain native-action failures remain preserved. [Evidence index](test_runs_20261001_pi_opening.json). Next: identify the concrete Pi event-pump exception and correct native ingestion/recovery, including the metadata-validation/ingress-deadline interaction if confirmed. No timeout, buffer, authority or qualification limits were relaxed. All milestone and release gates remain open.


## Real Connector Codex/Claude and terminal receipt publication - October 1, 2026

Connector ab1969b fixes default persisted discovery and publishes later durable Core receipt revisions, including restart recovery without native replay. Installed verification passed 252 Connector tests and 33 Nexus tests; 56 directed source cases passed. Nexus e272103 adds opt-in actual provider journeys through public parsed CLI onboarding, authenticated daemon realization, binding approval, admission, WSS and Core. Codex and Claude passed with renewed leases, three explicit operator decisions each, completed handoffs, successful turn/close receipts, normal daemon shutdown and protected credential cleanup. Pi failed after 392.27 seconds during opening and shutdown; a saved stack shows build-identity hashing in execution selection. All failed attempts remain in evidence, and the final Pi campaign credentials were removed. [Evidence index](test_runs_20261001_real_connector.json). Same Core a061960 / 0.2.43 and Nexus a0c6160 production wheel; Server readiness is fixture-only, native qualification unchanged. Next: correct the Pi opening/shutdown defect, then repeat the real provider campaign. This is a single Windows loopback host; no milestone or release gate closes.


## Positive runtime CLI dispatch and independent history reads - October 1, 2026

Connector 17ea012 permits historical operation queries after workspace/binding mapping changes using the current canonical identity, while refusing launch mutations with changed evidence. Credential rotation during a query discards the result. Nexus test commit 3dec14b verifies public parsed CLI open/submit/steer/interrupt/close through real loopback HTTP, automatic daemon WSS and Core: five operations and receipts, one native opening, one dispatch attempt per operation, identical command replay and final CLI receipt reads. Installed verification passed 246 Connector tests and 33 Nexus tests; pip check passed. [Evidence index](test_runs_20261001_runtime_cli.json). The native peer and Server readiness qualification are synthetic; actual remote Pi/Codex/Claude acceptance is still pending. An initial test assertion placed before all actions was corrected and retained. Nexus production bytes remain a0c6160; Core remains a061960 / 0.2.43. Next: actual remote provider journeys and remaining session reuse/observation/retention under M03/M04/M10. No milestone or release gate closes.


## Canonical runtime CLI admission - October 1, 2026

Connector ef124e6 adds schema 11 durable runtime intents and routes R4 start/submit/steer/interrupt/stop through canonical resolution and Server admission. Stable IDs, exact content, authority revalidation, lost-response recovery and scoped operation reads are tested without a local execution owner. Nexus a0c6160 returns structured intent/admission/read refusals. Installed verification passed 241 Connector tests and 32 Nexus tests plus CLI staging subprocess checks and pip check. [Evidence index](test_runs_20261001_runtime_admission.json). The TCP journey proves blocked resolution/replay and operation absence after approved binding; positive admission uses a technical peer and does not qualify remote provider execution. Core a061960 / 0.2.43 remains unchanged. Next under existing M03/M04/M10: session reuse, complete runtime observation/retention and actual admission/daemon provider journeys. Read recovery after physical mapping drift also remains pending. Start currently requires explicit new session and separate submit. No milestone or release gate closes.


## Durable public binding prepare/apply - October 1, 2026

Connector 2a52255 adds schema 10 binding intents, public prepare/apply with explicit reviewed hash and operator proof, stable retries after lost responses, scope revalidation and atomic local acknowledgment. Nexus 5d21a93 maps binding refusals to structured HTTP errors. Installed verification passed 224 Connector tests and 32 Nexus tests, including real loopback HTTP, operator approval and CLI subprocess show/list; pip check passed. [Evidence index](test_runs_20261001_binding_onboarding.json). The technical onboarding journey reaches APPLIED/BOUND without creating runtime sessions or outbox operations. Initial JSON-shape and HTTP error failures are retained. Core a061960 / 0.2.43 is unchanged. Next: canonical runtime CLI admission and reusable mapping, then actual remote Pi/Codex/Claude. Binding replacement/removal, remaining M03/M10 and all release gates remain open.


## Daemon-owned realization and public launch consent - October 1, 2026

Connector 80f65e0 adds configure-launch and realize commands. Realization travels through authenticated local IPC, remains owned after observer cancellation, uses the daemon bootstrap under a rotation gate, checks the daemon inventory and persists/replays one local publication intent. Nexus 0a0eee5 returns structured realization refusals. Final installed verification passed 212 Connector tests, 31 Nexus integration/binding/local-realization tests, CLI subprocess checks and pip check. [Evidence index](test_runs_20261001_executor_onboarding.json). The real loopback journey seeds identity/vault and uses a harmless discovery candidate; it starts no provider and ends PENDING_APPROVAL. Initial producer, registration-counter and ticket-rotation failures are retained and corrected. Core a061960 / 0.2.43 is unchanged. Next: durable public binding prepare/apply and reusable runtime CLI mapping, then real remote Pi/Codex/Claude. No milestone or release gate closes.


## Persisted Connector discovery and public CLI - September 30, 2026

Connector 74e9b48 adds schema 9 discovery configuration scoped to a registered Server executor. Public configure-discovery/discover commands and the automatic daemon use the persisted roots and Pi Node/release pair through Core's public discovery facade. Physical path replacement and configuration races are refused; naming an external Node file does not trust its whole directory. The final installed wheel passed 190 tests, pip check and separate CLI persistence/preview/refusal/clear processes. [Evidence index](test_runs_20260930_discovery_configuration.json). Nexus product 301ed04 and Core a061960 / 0.2.43 are unchanged. Next: public launch configuration and realization publication/acknowledgement, reusable binding onboarding, then real remote Pi/Codex/Claude journeys. M03/M10, M08 and release gates remain open.


## Lease-authorized remote native capture - September 30, 2026

Nexus 301ed04 and Connector f49d48e adopt Core a061960 / 0.2.43.dev0. The public Core factory derives native capture at launch from an applied R4 lease with both decision actions; Connector opts in before installing the lease. Installed tests passed: Core 65, Connector 78, Nexus 101 and 83 overlapping cases without Connector. Four new loopback WebSocket cases exercise canonical approval/input approval and denial through the automatic daemon with a technical native peer. Initial test-contract errors were corrected; an isolated lease-renewal timeout did not recur in the unchanged standalone test or sequential full rerun, but its cause remains undetermined. [Evidence index](test_runs_20260930_native_lease.json). Previous real Pi/Codex/Claude results belong to Core 0.2.42. Next: existing M03/M10 public Connector discovery/configuration/realization onboarding, then real remote provider journeys. No milestone or release gate closes.


## Real local Pi, Codex and Claude on Core 0.2.42 - September 30, 2026

Nexus 75f1af5 and Connector a308cf6 adopt Core c7aa63d / 0.2.42.dev0. Actual Codex permission was observed as an empty elicitation form; the validator now accepts that form only with an explicit response, without persistent permission metadata. Installed tests passed: Core 75, Connector 45, Nexus 83 and the same 83 overlapping cases without Connector. Real Windows journeys passed for Pi, Codex and Claude on the same installed Nexus/Core wheels, with completed handoffs, successful turns/closes and credential cleanup. Codex and Claude each required three explicit operator decisions; Pi used three native actions. Server release gates were test-only overridden; native qualification was unchanged. [Evidence index](test_runs_20260930_native_elicitation.json). Next: remote native capture under applied lease authority and remaining M08 acceptance. No milestone or release gate closes.


## Canonical native decisions and real Claude - September 30, 2026

Nexus dfa48d5 adds operator CAS, transactional decision/outbox admission, input retention and embedded native application on Core 0.2.41 (6cf2ecc); Connector remains ab6bfaf. Installed verification passed 83 cases in each overlapping normal/no-Connector campaign. The actual Claude journey passed with three explicit operator decisions, completed handoff, successful turn/close and credential cleanup. Codex still rejects the MCP call before any canonical request is captured; its handoff remains OPEN. The Windows standby interruption and all earlier failures are retained. See [M08 increment](M08_OPERATIONAL_NATIVE_PROPOSALS.md) and [test index](test_runs_20260930_native_decisions.json). Next: actual Codex request translation and remote capture under the applied lease. M08 and release gates remain open.


## Transactional native request ingress and Core adoption - September 30, 2026

Nexus 49b2422 and Connector ab6bfaf adopt Core 0.2.41 (6cf2ecc). [M08 ingress increment](M08_OPERATIONAL_NATIVE_PROPOSALS.md) persists intact operational proposals separately from redacted display, with scoped typed IDs, replay/conflict handling, fixed expiry and atomic event ACKs. Installed regressions passed 55 Nexus cases in each overlapping normal/no-Connector campaign and 45 Connector cases; pip checks passed. Initial inventory-version mismatch failures are retained. Operator CAS, native application, input retention and real Codex/Claude reruns remain pending. M08 and release gates remain open.

## Operational native proposals and Claude MCP permissions - September 30, 2026

[Core increment](M08_OPERATIONAL_NATIVE_PROPOSALS.md) published at 6cf2ecc / 0.2.41.dev0 separates the adapter-correlated operational proposal from its redacted display and prevents uncorrelated native payloads from creating approval authority. Claude MCP permission classification and stdio channel composition are covered. Clean package checks, 54 installed Core tests and pip check passed with both applications absent. At this Core-only publication, Nexus/Connector remained on 0.2.40; the subsequent adoption is recorded above. Canonical native decision integration remains pending. M08 and release gates remain open.

## Selected version observation and opening MCP handshake - September 30, 2026

[Increment](M05_MCP_OPENING_HANDSHAKE.md): Core 0.2.40 observes missing selected versions at the guarded launch frontier; Nexus permits bounded MCP initialization under an applied lease before READY while retaining domain gates. Installed regressions passed 101 Core, 45 Connector, 79 Nexus and 78 overlapping no-Connector cases (one Connector-only case deselected). Real Codex now reaches MCP ready; both Codex and Claude fail governed handoff completion because native tool permission decisions are not yet composed. Failure evidence and test-drain cleanup are retained. Next: complete the existing M08 native approval/input path and rerun the real journeys. No milestone or release gate closes.

## Process-only MCP with approved existing login - September 30, 2026

[Increment](M05_PROCESS_HTTP_LOGIN.md): Core 0.2.39.dev0 composes bounded process-only MCP arguments for Codex/Claude while preserving approved local login. Nexus and Connector select this mode for approved provider homes without imported provider secret references. Installed campaigns passed 83 Core, 45 Connector and 15 Nexus cases, plus the overlapping 15-case no-Connector campaign; clean artifact verification and pip check passed. Real Codex/Claude integration is pending. No milestone or gate closes here.

## Real embedded Pi and local discovery configuration - September 30, 2026

[Increment](M05_REAL_EMBEDDED_PI.md): serve now accepts explicit local discovery roots and the Node/Pi installation pair. The real Pi 0.87.1 journey passed through the automatic embedded owner, public binding/grant/admission, applied lease renewal, actual native extension tools, canonical handoff completion, successful turn/close receipts and protected credential cleanup. The installed proof ran outside the repository with no Connector installed and no native build qualification override. The Server release gate remains test-only overridden. Installed regressions passed 38 cases in each overlapping normal/isolated campaign; the installed real-provider case passed separately. Discovery freshness and test-configuration failures are retained. Core/Connector packages are unchanged. Codex/Claude, remote and other fixed-plan acceptance remain open; no milestone or gate closes here.

## Native capability refresh after applied renewal - September 30, 2026

[Increment](M09_NATIVE_CAPABILITY_REFRESH.md): automatic Pi composition in Nexus and Connector now refreshes capability metadata under the exact applied Server/Core lease, retaining the original material, scope and actions. Core still validates every domain effect; stale metadata, revocation and a concurrent lease change refuse it. Installed campaigns passed 58 Nexus cases, 49 overlapping cases with no Connector installed, and 81 Connector cases, with pip check. Initial fixture-related restart failures and corrected final reruns are preserved. Connector is published at 40049af; Core remains fb4c8df / 0.2.38.dev0 with the same shared wheel. Full real-provider journeys and the remaining fixed-plan criteria stay open; no milestone or gate closes here.

## Serve-owned session tools and automatic MCP — September 30, 2026

[Increment](M05_EMBEDDED_TOOLS.md): the local dispatcher reserves canonical session capabilities under its store owner, persists material in the protected vault before native configuration, and composes checked per-session MCP homes or the existing Pi action owner. Confirmed close removes material; uncertain ownership retains it. The automatic Codex technical peer exercised real MCP identity, handoff claim/completion and a repeat call after automatic lease renewal. Installed results: 133 passed; 70 overlapping cases passed without Connector, with pip check. A separate installed SessionToolVault/Windows Credential Manager roundtrip passed with cleanup. Full Claude/Pi qualification, Pi deadline refresh, live configuration recovery and remaining M05/M09 acceptance remain open. Core/Connector artifacts are unchanged; no gate closed.


## Protected local provider credentials — September 30, 2026

[Increment](M05_PROVIDER_VAULT.md): local owner CLI stores/removes provider secrets in the protected OS credential store with installation/agent isolation. ApprovedLocalLaunch resolves vault references off-loop and retains its authority/configuration checks around resolution. Installed results: 122 passed; 67 overlapping cases passed without Connector, with pip check. Actual Windows Credential Manager and separate installed CLI process roundtrips passed with credential cleanup and no plaintext file/output. Initial source failures and corrections are retained. Session tool capability composition, Linux/macOS vault qualification and full M05 remain open; Core/Connector artifacts are unchanged.


## Embedded released-resource reconciliation — September 30, 2026

[Increment](M05_EMBEDDED_RESOURCE_RECONCILIATION.md): serve verifies retained Core journals, claims, released global slots and recovered event watermarks before submitting proofs to canonical reconciliation. Its readiness transaction checks the current embedded owner/epoch. A proven release closes the old session and enables a new public admission with the approved binding after restart. Occupied/missing stores, untracked journals and pending event gaps retain RECOVERING. Installed results: 113 passed; 58 overlapping tests passed without Connector, with pip check. Uncertain native processes, complete tools/governance and real-provider journeys remain required. Core/Connector artifacts are unchanged; M05/G1 remain open.


## Embedded event publication and cold replay — September 30, 2026

[Increment](M05_EMBEDDED_EVENTS.md): migration 085 registers local streams before native open. Serve maintenance publishes bounded Core event pages through canonical Nexus ingress under the current owner, then applies durable ACKs to Core. Restart reapplies committed ACKs and replays uncommitted native events without loading the provider. Installed results: 108 passed; 53 overlapping tests passed without Connector installed, with pip check. Resource/slot reconciliation, full event consumption, tools/governance and complete provider journeys remain required. Core/Connector artifacts are unchanged; M05/M07/G1 remain open.


## Embedded historical receipt recovery — September 30, 2026

[Increment](M05_EMBEDDED_RECOVERY.md): serve startup publishes pending Core journal facts before considering dispatch, without loading the provider or constructing a runtime. Current-owner persistence validates the immutable historical binding and original applied dispatch lease. Missing journals retain recovery state; canceled observers cannot abandon history journals. Installed results: 89 passed; 50 overlapping tests passed without Connector installed, with pip check. Slot/resource and event reconciliation remain required before retained stores become ready. Core/Connector artifacts are unchanged; M05/G1 remain open.


## Automatic embedded outbox dispatch — September 30, 2026

[Increment](M05_EMBEDDED_DISPATCH.md): serve startup now composes the canonical local outbox pump, approved Core launch, lease installation/ACK, independent renewal and durable receipt publication. Failures return the current owner to RECOVERING; retained shutdown drains native work even after a pump cleanup error or canceled observer. Remote reconciliation retry now resets the unavailable cached snapshot under the current owner. Final installed results: 135 passed; 47 overlapping tests passed in the actual no-Connector environment, with pip check. Technical native and qualification fixtures remain; cold recovery, historical-owner publication, events/tools/vault/governance and complete provider journeys are still required. Core/Connector artifacts are unchanged. M05 and G1 remain open.


## Approved local launch configuration — September 30, 2026

[Increment](M05_LOCAL_LAUNCH.md): the serve-composed Core host resolves the persisted approved local mapping before acquiring runtime stores and revalidates configuration/authority around secret resolution. Canonical digests, candidate fingerprint, physical directories, profile, agent and current owner are checked. Core open uses approved auth references and environment. Installed results: 78 passed; 36 overlapping cases passed in the actual no-Connector environment, with pip check. The positive case uses public binding/admission and canonical leases, but a technical native factory, forced readiness and manual reserve/begin. Automatic embedded dispatch, vault/tools, receipts/events, renewal/recovery and full M05/G1 remain open. Core/Connector artifacts are unchanged.


## Public embedded realization preparation — September 30, 2026

[Increment](M05_LOCAL_REALIZATION.md): authenticated operators can prepare local workspace/configuration evidence through the existing realization route, then approve the canonical binding. Migration 083 stores private local mapping and protected secret references atomically with canonical realization records. Owner/agent checks run before filesystem access and again before commit; changed request, candidate or directory is refused. Serve restart reuses the same realization. Installed regression: 69 passed; the actual environment without Connector passed 27 overlapping cases and pip check. No native session or runtime readiness is introduced. Local dispatch/lease consumption and full M05/G1 remain open. Core/Connector artifacts are unchanged.


## Serve-owned embedded inventory — September 30, 2026

[Increment](M05_EMBEDDED_INVENTORY.md): the real serve lifecycle discovers local candidates and publishes path-free inventory under its existing store owner, with transactional epoch/generation/revocation checks, periodic refresh and retained cleanup. Public inventory/runtime-options routes expose local facts to active agents. Restart republishes under the successor owner. Installed affected regression: 55 passed; a fresh Nexus serve-lite/Core environment with no Connector module or distribution passed 13 overlapping cases and pip check. No Core runtime store or WSS ticket is opened for inventory. Core/Connector artifacts are unchanged. Local dispatch, realization/configuration and M05/G1 acceptance remain open; the embedded executor stays RECOVERING.


## Automatic runtime lease renewal — September 30, 2026

[Increment](M06_RUNTIME_LEASE_RENEWAL.md): the automatic daemon renews live sessions using Server grants and Core deadlines, revalidates local authority and retains renewal producers during shutdown. Compatible Server renewal keeps applied authority until ACK, including dispatch and session tools. Core 0.2.38 publishes coherent session/R4 contexts before post-CAS I/O. Final installed results: Core 154 passed; Connector 417 passed and one existing skip; Nexus 144 passed. Real Pi 0.87.1, Codex 0.159.0 and Claude 2.1.282 completed local Core turn/renewal/terminal-close probes with locally constructed grants. The initial installed Nexus failure remains recorded; it is resolved in the final run. Same Core wheel in both consumers. Full provider journeys, live-session adoption, rotation and remaining fixed-plan acceptance are pending. No milestone or gate closed.


## Durable resource release and automatic reconciliation — September 30, 2026

[Increment](M06_RESOURCE_RELEASE.md): Core 0.2.36 exposes retained slot state and correlates release with the original opening. Connector reports that fact after lease cleanup; Nexus verifies it and closes session state without synthesizing a close operation or receipt. Real HTTP/WSS recovery returns to control readiness with unchanged native/operation counts. Installed results: Core 140 passed; Connector 410 passed (one existing skip); Nexus 87 initial passes plus the corrected bootstrap pin test passing on focused rerun (88 distinct cases). The initial Nexus failure and rerun remain in the manifest. All three production wheels updated; identical Core wheel in both consumers. Live-session adoption, unknown ownership and full acceptance remain pending.


## Granted lease retention after WSS loss — September 30, 2026

[Increment](M06_DISCONNECTED_LEASES.md): automatic transport-loss cleanup retains Core runtimes until their installed leases expire, are revoked, close or release ownership. Unknown state and inspection failures retain cleanup; an explicit daemon stop uses normal shutdown. All started inspections remain owned through errors. Real HTTP/WSS coverage verifies no premature native stop and no repeated work. Final installed results: Connector 410 passed (one existing skip), Nexus 75 passed. Core/Nexus production wheels unchanged. Live-session adoption and durable release evidence remain pending; no milestone or gate closed.


## Durable ticket recovery after daemon recreation — September 30, 2026

[Increment](M06_TICKET_RECOVERY.md): lane startup and receipt/event recovery share persisted non-secret ticket intents. Lost material is recovered with the original logical intent and a new credential request, under unchanged Server replacement rules. Two HTTP/WSS cases recreate the daemon without its retained cache and recover pending events without native replay or expiry injection. Installed results: Connector 404 passed (one existing skip), Nexus 74 passed. Core/Nexus production wheels unchanged. Process-kill qualification, active ownership, full rotation, embedded publishing, projections and final acceptance remain pending. No milestone or gate closed.


## Pending events during daemon reconnect — September 30, 2026

[Increment](M07_EVENT_RECOVERY.md): the daemon attaches current lanes and drains persisted event obligations before reconciliation. Existing valid in-memory tickets retain their original deadlines. Lane proofs transfer before the normal reader starts. Real HTTP/WSS tests cover an undelivered event and a lost ACK, with automatic reconnect and unchanged native operation counts. Installed results: Connector 380 passed (one existing skip), Nexus 72 passed. Nexus/Core production wheels unchanged. Cold restart with unavailable active ticket material, active ownership, embedded publishing, projections and full acceptance remain open.


## Automatic event publisher and ACK recovery — September 30, 2026

[Increment](M07_EVENT_PUBLISHER.md): Connector registers streams before native opening, owns bounded finite-journal publishers and persists remote/Core-applied ACK cursors separately. Retries recover without another event or runtime operation. Exact ACK targets share the owned WSS reader. Nexus and Connector now reconcile fully acknowledged nonzero streams for confirmed closed sessions. Installed results: Connector 375 passed (one existing skip), Nexus 70 passed. Core 0.2.35 unchanged. Unacknowledged-stream reconnect recovery, active ownership, embedded publishing, projections and full acceptance remain open.


## Durable WSS event ingress — September 30, 2026

[Increment](M07_EVENT_INGRESS.md): Nexus validates the current owner and binding lane, retains canonical events with conflict detection, computes the contiguous watermark with the public Core reducer, and sends ACK only after the transaction commits. Public HTTP/WSS coverage verifies out-of-order arrival and replay. Installed focused regression: 65 passed, no skips. Connector/Core unchanged. Automatic publishers, local Core ACK recovery, projections and nonzero-stream reconciliation remain pending; NS10.01 and full delivery gates remain open.


## Confirmed close and paged reconciliation — September 30, 2026

[Increment](M06_M07_RECONCILIATION.md): Connector schema 3 retains acknowledged hash associations and opening generation/epoch. A fresh Core owner reconciles confirmed closed sessions and 264 receipt summaries over real HTTP/WSS without native replay. Server readiness checks durable receipt integrity, current ownership, pagination and remaining sessions. Installed results: Connector 356 passed (one existing skip), Nexus 114 passed. Core 0.2.35 is unchanged and its wheel is identical in both consumers. Active session adoption, event replay, rotation and full acceptance remain pending. No milestone or gate closed.


## Receipt recovery from Core facts — September 30, 2026

[Increment](M07_RECEIPT_BINDING.md): Core 0.2.35 validates a non-secret association between Core and R4 hashes before effects. Connector persists it, migrates publication storage to schema 2, and reconstructs pending receipts from the journal at startup. Installed results: Core 104 passed, Connector 353 passed (one skip), Nexus 84 passed. Recovery after Core commit/before wire persistence is verified through real HTTP/WSS with a technical peer. Nonempty session reconciliation, acknowledged-operation history, rotation and full acceptance remain pending.

## Durable Connector receipt publication — September 30, 2026

[Increment](M07_DURABLE_PUBLICATION.md): reserve before Core effects, persist projected receipts before HTTP, and replay ready pages at startup using fresh scoped authority. Installed tests: Connector 349 passed (one existing skip), Nexus 83 passed. Lost delivery/acknowledgment, retained writes, startup ordering, authorization changes and 257 receipts are covered. Unprojected reservations, nonempty session reconciliation, ticket rotation and full acceptance remain open.

## Late close publication — September 30, 2026

[Increment](M07_LATE_CLOSE_PUBLICATION.md): daemon and embedded owners await the retained Core close producer through durable terminal completion. Installed tests: Core 78, Connector 337 (one skip), Nexus 81. Deadline, cancellation and injected storage failure paths are covered. Disconnect/restart recovery and full acceptance remain open.

## Terminal R4 close — September 30, 2026

[Increment](M07_TERMINAL_CLOSE.md): Core 0.2.33 persists terminal close and the daemon publishes SUCCEEDED through the public operation query. Installed regressions: Core 76, Connector 336 (one skip), Nexus 81. Real Pi/Codex/Claude close receipts are SUCCEEDED. Delayed/disconnected publication and full acceptance remain pending.

## Native close outcomes — September 30, 2026

[Correction](M11_NATIVE_CLOSE_OUTCOMES.md): Core 0.2.32 reports confirmed normal/forced stop instead of losing the adapter outcome. Installed Core 966 passed / 74 skipped; Connector 336 passed / one skipped; Nexus 81 passed. Codex/Claude real R4 close accepted without receipt errors. Terminal close publication and full product acceptance remain open.

## Core 0.2.31 and Codex 0.159.0 — September 30, 2026

[Increment](M01_CODEX_0159_QUALIFICATION.md): exact Windows Codex qualification and matching Core wheels in both consumers. Installed tests: Core 951 passed / 74 skipped; Connector 336 passed / one skipped; Nexus 81 passed. Real Pi/Codex/Claude turns succeeded under locally installed R4 grants. Close classification and full Server journeys remain open. No full milestone or gate closed.

## Local real harnesses — September 30, 2026

[Campaign](LOCAL_HARNESS_CAMPAIGN.md): Pi, Codex and Claude completed native protocol tests. Installed factory: Pi succeeded; Claude turn succeeded with an initially unknown close; Codex 0.159.0 was refused as unqualified. Real R4 end-to-end acceptance and the complete delivery gates remain open.

## Automatic daemon lanes — September 30, 2026

[Implementation and limits](M06_AUTOMATIC_LANES.md): installed Connector 336 passed / one skipped; Nexus 81 passed. Initial attachment and execution now start from approved persisted bindings. Renewal and nonempty reconciliation remain open. No milestone or gate closed.

## Metadados e recuperação de capability — 30 de setembro de 2026

O [incremento](M02_CAPABILITY_RECOVERY.md) implementa consulta HTTP sem
material e recuperação explícita do segredo no vault. O Server exige
autoridade ativa/aplicada; o Connector compara lease ID/serial com o Core
e limita a validade pelo menor prazo. GET não renova, emite ou substitui.

Passaram 283 testes Connector (um skip existente) e 73 Nexus com wheels
instalados e bytes conferidos. O teste recupera o mesmo segredo após
recriar o owner, inclusive com renovação aplicada, e consulta o domínio.
Revogação, serial divergente, metadata inválida e vault vazio são recusados.

O build inicial herdou assets antigos; ambos os runners pararam antes de
pytest. A reconstrução em staging limpo e os resultados finais estão no
[manifesto](test_runs_20260930_capability_recovery.json). A consulta adiciona
uma rota às 23 originais; o contrato e a cobertura passam a 24 rotas.

Composição automática, reconciliação não vazia do daemon, agendamento de
recuperação/renovação e retenção terminal permanecem pendentes. Não há
aceite de restart completo, provider real ou fechamento de gates.


## Emissão durável no Connector — 30 de setembro de 2026

O [incremento de intenção durável](M02_DURABLE_CAPABILITY_INTENT.md) acrescenta
schema 7, owner de emissão e composição pela porta de abertura existente.
O ID é persistido antes do POST; o segredo é armazenado no vault antes de
liberar configuração. Cancelamento não abandona a gravação. Replay recupera
metadados pelo mesmo ID e não substitui segredo após envio incerto.

A [campanha instalada](test_runs_20260930_capability_reservation.json) passou
275 casos Connector (um skip existente) e 61 Nexus. Os testes incluem a
transação canônica de emissão com resposta perdida e a corrida entre
armazenamento do segredo e metadados recebidos por outro owner.

O material persiste, mas sua reutilização após restart depende da
reconciliação de autoridade ainda pendente. Configuração aprovada automática,
renovação e retenção/limpeza terminal também continuam obrigatórias. O
incremento não encerra M02/P6.1 nem gates de produto.


## Pi nos hosts e shutdown — 30 de setembro de 2026

O [incremento Pi](M09_PI_HOST_OWNERSHIP.md) integra o owner público do Core
0.2.30.dev0 aos hosts embedded e Connector. O child Node técnico usa a
extensão empacotada para contexto/claim/complete. Timeout e cancelamento
da espera conservam os produtores; journal e ledger permanecem abertos
enquanto houver efeito de domínio pendente.

A campanha Nexus instalada foi reexecutada antes desta publicação: 33 passes.
As evidências anteriores conferidas registram Core 143 passes, Connector
264 passes e um skip, e embedded com imports Connector bloqueados: dois passes.
O [manifesto coordenado](test_runs_20260930_pi_owner.json) distingue tentativas,
artefatos e limites. Os casos são sobrepostos e não qualificam provider real.

O teste embedded usa uma fixture WSS para autoridade, portanto o aceite
local puro ainda exige composição canônica no serve. Configuração aprovada,
intenção durável de segredo, startup automático de execução, renovação,
reconciliação não vazia e os demais critérios M00–M13 permanecem pendentes.
Nenhum milestone integral ou gate foi encerrado.


## Bridge nativa Core — 30 de setembro de 2026

O [incremento](M09_CORE_NATIVE_BRIDGE.md) conecta a bridge pública do Core
0.2.29.dev0 ao domínio canônico por dois backends: Nexus embedded e Connector
HTTP. O escopo da capability é limitado pela autoridade instalada no runtime;
o caller preserva IDs e não repete automaticamente mutações incertas.
O teste embedded também recusa todos os imports do aplicativo Connector.

A campanha ampla revelou uma disputa de leitura/escrita do state.json no
Windows. A leitura agora usa o mesmo lock da escrita; o teste controlado
reproduziu a ausência de exclusão antes da correção.
Os resultados finais, a falha original e os artefatos estão no
[manifesto](test_runs_20260930_native_domain.json). A composição automática
dos hosts, o ciclo do socket Pi e a renovação de capabilities permanecem
pendentes. Nenhum milestone ou gate é encerrado.


## Ações nativas canônicas — 30 de setembro de 2026

O [incremento nativo](M09_NATIVE_ACTIONS.md) adiciona a rota pública de
contexto/claim/complete com audiência própria e ledger transacional de
pedidos/resultados. MCP e ações nativas disputam o mesmo claim e podem
concluir trabalho adquirido pelo outro canal quando o escopo da sessão é
o mesmo. A migration 082 é aditiva.

A [evidência](test_runs_20260930_native_actions.json) registra as tentativas,
correções, regressões e teste do wheel instalado. A adoção pelo daemon,
executor embedded e bridge Pi permanece pendente, junto com inbox e demais
ferramentas, causalidade completa e aceites de provider. NS03.04/NS12.01/
NS12.02 continuam parciais; nenhum gate ou flag foi promovido.


## Plano de entrega total — checkpoint após integração MCP

O [plano completo](DELIVERY_PLAN.md) mantém 14 milestones, 13 lotes,
85 tarefas Nexus, 164 cenários originais, 12 entregas Core/Connector e
quatro cenários de idioma. O checkpoint foi atualizado para Nexus
`c979095`, Connector `c97c9d4` e Core `9d244cf`.
Os critérios de saída dos lotes agora estão explícitos também no JSON.
A fila detalha ações nativas e paridade de claims com MCP antes da adoção
pelos hosts, preservando as dependências de fechamento dos marcos.

A [verificação documental](full_delivery_checkpoint_20260930.json) registra
hashes, cobertura e evidência histórica conferida. Esta revisão não executa
testes de produto nem fecha G0–G3. Permanecem obrigatórios os ciclos local
sem Connector, remoto em hosts independentes, providers reais, UI/CLI,
recuperação, migração/rollback e todos os textos próprios em US English.


## Autoridade MCP de sessão — 30 de setembro de 2026

O [incremento de handlers MCP](M09_MCP_SESSION_AUTHORITY.md) integra oito
ferramentas ao escopo R4, revalida autoridade no UOW do domínio e vincula
claim/complete à sessão e à geração canônicas. Chaves tools-only continuam
separadas. NS03.04/NS12.01/NS12.02 permanecem parciais: faltam ações nativas,
inbox limitado ao workspace, demais ferramentas e adoção pelos hosts.
O [manifesto](test_runs_20260930_mcp_capabilities.json) registra campanhas,
falhas corrigidas, hashes e limites. Nenhum gate foi encerrado.


## Capabilities de sessão — 30 de setembro de 2026

A [emissão canônica](M02_SESSION_CAPABILITIES.md) agora retorna segredo único,
escopo/revisões e audiência de sessão. A aplicação legítima de lease mantém
a validade do mesmo token; o cliente Connector valida o DTO e o prazo.
Passaram 343 regressões Connector (dois skips existentes), 137 casos Nexus R4
e 120 casos instalados nos bytes finais.
As campanhas se sobrepõem; o [manifesto](test_runs_20260930_capabilities.json)
preserva as tentativas e seus limites. NS03.04 permanece parcial: falta o guard
nos handlers MCP/nativos e a composição aprovada do ambiente do daemon.
Nenhum gate foi encerrado.

## Plano de conclusão revisado — 30 de setembro de 2026

O [plano coordenado](DELIVERY_PLAN.md) foi revisado sobre Nexus `fb2c2d1`,
Connector `9e1a96a` e Core `9d244cf`. A sequência P1–P13 agora explicita
os lotes até o aceite final; P6.1–P6.5 detalham configuração aprovada,
composição automática, renovação, recuperação e integração instalada.
A [revisão registrada](completion_review_20260930.json) distingue inspeção
de código/evidências de execução de testes. Esta atualização é documental;
nenhuma tarefa de implementação ou gate foi encerrado por ela.

As seções abaixo preservam o contexto de cada incremento na data em que
foi testado. Para pendências atuais, usar o checkpoint e a fila do plano.

## Startup automático do controle R4 — 30 de setembro de 2026

O [startup do daemon](M06_DAEMON_STARTUP.md) agora usa o registro persistido,
negocia o canal e publica o inventário com sequência durável. O Nexus autoriza
a troca de produtor somente pelo canal reconciliado atual e revalida a
autoridade no commit. A jornada real prova dois boots, HTTP/WSS e IPC, sem
criar operações ou lanes implicitamente. Evidências e limites estão no
[manifesto coordenado](test_runs_20260930_startup.json). O startup automático
da execução, a configuração aprovada e a reconciliação não vazia continuam
pendentes. G0–G3 permanecem abertos.


O [plano de entrega completa](DELIVERY_PLAN.md) organiza a conclusão dos três repositórios em 14 marcos e preserva todos os requisitos R4. A [cobertura validada](delivery_coverage.json) associa tarefas e testes aos marcos; não declara novos testes de produto executados nem encerra gates.

## Incremento corrente — registro durável do executor pela CLI

O [registro M02/M06](M02_EXECUTOR_REGISTRATION.md) persiste intenção/resultado
no schema Connector 5, recupera o mesmo executor após repetição e disponibiliza
bootstrap process-local com prazo capturado antes do HTTP. A CLI importa
identidade e registra/lista/consulta usando o Server real. `identity add` agora
preserva o perfil autenticado necessário aos comandos seguintes.

Passaram 300 regressões Connector com dois skips, 40 casos dirigidos, 104
casos Nexus R4 e 78 casos instalados fora dos clones, com sobreposição.
O [manifesto](test_runs_20260930_registration.json) fixa comandos, estado e
hashes. O registro não cria lane ou lease. Startup automático do daemon,
renovação, reconciliação e ambiente de produção continuam pendentes; nenhum
gate foi fechado.

## Incremento anterior — operações sob ownership do daemon

O [owner de execução M04/M06](M06_DAEMON_EXECUTION_OWNER.md) recebe operações
do reader WSS, instala a lease antes de abrir e traduz sete ações pelos
contratos públicos Core. O daemon preserva produtores após cancelamento e
observa sua conclusão antes de fechar o host. Falha de publicação encerra o
canal sem repetir o efeito.

Passaram 286 regressões Connector com dois skips, 17 contratos/casos dirigidos,
103 casos Nexus R4 e 63 casos instalados fora dos clones, com sobreposição.
O [manifesto coordenado](test_runs_20260930_execution_owner.json) preserva
tentativas, correções e hashes. A jornada WSS passou a admitir/consultar
operações, deixando a execução e os receipts a cargo do consumidor do daemon.
Startup automático, credenciais/renovação, ambiente de produção, reconciliação
e publicadores duráveis continuam pendentes. Nenhum gate foi fechado.

## Incremento anterior — seleção física aprovada no Connector

O [incremento M03/M06](M06_PHYSICAL_SELECTION.md) persiste o resultado aprovado
do binding e resolve a instalação/workspace contra a evidência local completa.
O host revalida após esperas e ao reutilizar o cache, antes de compor pelo Core
público. A jornada WSS usa esses serviços e confirma uma abertura na pasta
aprovada, somente depois de instalar a lease.

Passaram 27 casos dirigidos e 278 regressões do Connector, com dois skips;
103 casos Nexus R4 e 55 casos instalados fora dos clones, com sobreposição.
O [manifesto](test_runs_20260930_physical_selection.json) preserva falhas
iniciais de fixture, resultados, comandos e hashes. Schema Connector 4 exige
backup para downgrade; o ensaio completo fica em M12. Daemon/CLI, perfil e
ambiente canônicos, refresh de revisões, embedded e reconciliação não vazia
continuam pendentes. Nenhum gate ou flag de prontidão foi promovido.

## Incremento anterior — owner de conexão R4 no Connector

O [owner M06](M06_CONNECTOR_CONNECTION_OWNER.md) recebe operações e correlaciona
leases/attaches pelo mesmo reader. Possui filas limitadas, revalidação de lane,
proteção dos produtores contra cancelamento e confirmação ordenada do commit
de `lease.applied` antes de liberar execução e receipts por outro canal.

Passaram 13 contratos/ciclos de vida e 28 casos instalados, com sobreposição.
A jornada pública percorre cinco ações em WebSocket real de loopback e Core
com peer sintético. A repetição instalada encontrou uma corrida entre ACK e
receipt HTTP; o Connector foi corrigido e a campanha passou. O manifesto
coordenado preserva as tentativas e hashes. Daemon/StateStore, resolver físico,
embedded e reconciliação não vazia continuam pendentes. Nenhum gate foi fechado.

## Incremento anterior — loop WSS com owner persistido

O [incremento M04/M06](M04_REMOTE_DISPATCH_PUMP.md) liga a admissão ao loop
real de envio do Server. A jornada pública percorre open/submit/steer/interrupt/
close com Core e peer sintético. Desconexão mantém o mesmo ID em reconciliação,
sem segundo envio. Reservas possuem owner/geração; cancelamento do waiter não
abandona o produtor de banco e a autoridade é revalidada após esperar o writer.

Passaram 102 testes R4 no rerun completo, sete de migração e 70 instalados
fora dos clones, com sobreposição. Tentativas com falha de harness assíncrono
e expectativa antiga de efeito possível foram preservadas e corrigidas.
O [manifesto](test_runs_20260930_dispatch_pump.json) fixa comandos e hashes.
Daemon, resolver físico, embedded, reconciliação não vazia e aceites finais
continuam pendentes. Nenhum gate ou flag de prontidão foi promovido.

As seções seguintes são checkpoints históricos; a referência a loop pendente
na campanha de bootstrap descreve seu estado antes deste incremento.

## Incremento de abertura inicial sem dependência circular

O [bootstrap M04/M06](M04_OPEN_BOOTSTRAP.md) entrega runtime.open pendente
de lease, mantendo grant/conexão e reserva persistidos antes do envio.
Core recusa o contexto antes da instalação; o ACK associa lease e outbox
atomicamente e o receipt projeta a sessão. Replay não faz outro envio.

Passaram 97 casos R4, sete de migração e 46 instalados fora dos clones,
com sobreposição. A jornada pública cria binding/grant/operação pelas rotas
reais e abre/envia com Core e peer sintético. A tentativa instalada anterior
falhou no preflight por arquivos jsonschema ausentes; venv novo passou.
Loop de outbox, owners embedded/daemon e aceites finais continuam pendentes.
Nenhum gate ou flag de prontidão foi promovido.

## Incremento de prova delegada publicado

O [relatório M02/M03](M03_DELEGATED_BINDING.md) publica a prova transacional
de operador e os testes já registrados: 86 R4, 48 de aprovação, sete de
migração e 27 instalados, com sobreposição. Fonte e XMLs foram conferidos
contra os hashes da campanha; a revisão não representa uma nova execução.
Reuso de binding, lease inicial e composição do dispatcher/owners continuam
pendentes; nenhum gate foi encerrado.

## Planejamento de entrega total — revisão corrente

O [plano completo](DELIVERY_PLAN.md) foi atualizado com Nexus 777de37,
Connector 40a8cb0 e Core 9d244cf. Preserva os 14 marcos, 85 tarefas,
164 cenários originais, 12 entregas externas e quatro cenários de idioma.
Inclui lotes imediatos, matriz local/remota por provider/SO, limites de carga,
riscos, migração, rollback e aceite sobre os artefatos finais.

A prova delegada de operador está implementada no workspace Nexus e ainda
não foi commitada. A [revisão de evidência](planning_review_20260930.json)
conferiu hashes de fonte/XML e os resultados registrados: 86 casos R4,
48 de aprovação, sete de migração e 27 instalados, com sobreposição.
O Connector já publicou os DTOs e a correção do teste de pacote: a campanha
completa anterior teve uma falha e dois skips; os dois testes de pacote
passaram após a correção. Nenhuma suíte de produto foi reexecutada nesta
revisão documental.

Publicação/revisão do incremento pendente, reuso autorizado de binding,
lease inicial, outbox e owners de execução são a fila imediata. G0–G3
continuam abertos. As seções abaixo registram checkpoints históricos;
referências a prova delegada pendente descrevem o estado anterior.

## Incremento de onboarding por operador

O [incremento M02/M03](M03_OPERATOR_BINDING.md) permite prepare/apply pelo
operador autenticado representando o sujeito, com perfil/endpoint habilitados,
CAS, auditoria e rollback transacional. O grant é emitido separadamente pela
API existente; não foi semeado no teste. Passaram 77 casos Nexus R4 e 11 com
wheel instalado fora dos clones. Prova delegada, self-bind autorizado e
composição do ciclo de execução permanecem pendentes.

A campanha Core instalada de 99 passes foi revisada, reexecutada e publicada
em `9d244cf`; o wheel/runtime não mudou. Esses resultados não encerram M01,
M03 ou G0–G3. A revisão documental abaixo é um checkpoint histórico.

## Revisão do plano de entrega total

O plano foi consolidado contra Nexus `2baeaf9`, Connector `0be7faf` e Core
`368c50d`, com o mesmo hash do wheel Core `0.2.28.dev0` recalculado nos três
repositórios. A fila vigente começa pela conclusão da auditoria/conformance,
seguida de aprovação e perfil no onboarding público, abertura inicial com
lease e composição do dispatcher com os owners embedded/daemon.

A campanha local Core instalada registra 99 passes, mas runner/evidências
ainda não estão versionados. Sua revisão/publicação faz parte do próximo
incremento. Esta revisão documental não reexecutou testes de produto nem
encerrou M00/M01 ou G0–G3. As seções seguintes são registros históricos;
as prioridades atuais estão em [DELIVERY_PLAN.md](DELIVERY_PLAN.md).

## Incremento de contenção durante renovação pendente

O [incremento Core 0.2.28](M01_PENDING_CONTAINMENT.md) permite interrupt,
close e respostas estritamente negativas durante CAS de renovação do mesmo
escopo, sem manter locks de sessão aguardando storage. Trabalho produtivo,
conexão/escopo alterados, ação retirada e revogação continuam bloqueados.
Renovação tardia não confirma sessão drenando/fechada. O mesmo wheel foi
instalado nos dois consumidores.

Core completo: 920 passes/74 skips; novos casos instalados: 12 passes;
Nexus R4: 69 passes; integração instalada: 19 passes. Há sobreposição.
A porta CAS fica retida nos testes; isso não prova admissão paralela por
writer SQLite bloqueado. Conformance integral, onboarding, loop de outbox,
owners e qualificação real continuam pendentes. G0–G3 permanecem abertos.

## Incremento de controles canônicos

Steer e interrupt agora passam por resolução/admissão HTTP, targeting do Core,
reserva e autorização de dispatch. O frame validado preserva alvo, ID e hash;
o cliente Connector verifica a correlação antes de admitir a operação.
Interrupt previamente permitido continua despachável após expiry produtiva
com autoridade e lane válidas, sem exigir nova descoberta de binário.
O [ADR 0003](../../docs/adr/0003-canonical-control-targets.md) registra o mapping
de razão e política. O incremento seguinte resolve razão longa/vazia e close
com política; NS06/M04 permanecem parciais, com loop de outbox, decisões,
owners e campanhas finais pendentes.

## Incremento de fechamento canônico com política

Core `0.2.27.dev0` aplica política por sessão, conserva um producer após
cancelamento do waiter e confere razão/tempos no hash dos recibos. Nexus
resolve/admite/autoriza close e projeta sessão/lease fechadas na transação
do recibo, somente após fato de encerramento do owner corrente. Unknown
e progresso não fecham a sessão. Os consumidores usam o mesmo wheel.

O [relatório de close](M01_CLOSE_POLICY.md) registra a regressão Core de
fonte (908 passes/74 skips), Nexus R4 (69 passes), testes instalados Core
(21 passes) e integração instalada (19 passes), sem somar sobreposições.
Os testes ainda usam qualificação e peer sintéticos; não demonstram daemon,
provider, dois hosts ou UI. CAS pendente, composição dos owners e gates
M01/M04/G0–G3 continuam abertos.

## Execução do plano de entrega

A [auditoria M00](M00_AUDIT.md) iniciou coleta e revisão de aceite. O
[incremento M01 de decisões](M01_DECISION_CONFORMANCE.md) corrigiu a
incompatibilidade entre propostas nativas e o preview R4, publicou Core
`0.2.23.dev0` e sincronizou o mesmo wheel nos consumidores. Os 42 testes R4
do Nexus passaram com esse artefato. M00 e M01 permanecem `IN_PROGRESS`;
dispatcher canônico, contexto/grant completo, daemon e campanhas finais
ainda não estão aceitos. Os [resultados de regressão](test_runs_20260929.json)
registram falhas e skips sem convertê-los em aprovação.

## Incremento de targeting e inventário

Core `0.2.24.dev0` publica targeting pelo registry, valida os controles no
runtime e gera schema fechado de inventário v2 com os campos previstos no
plano. Nexus revalida evidência persistida antes de novos efeitos; Connector
consome o mesmo catálogo. A evolução está documentada no
[ADR 0002](../../docs/adr/0002-core-inventory-format-evolution.md).
O [relatório deste incremento](M01_TARGETING_INVENTORY.md) registra artefatos,
testes e limites. M00/M01 e G0–G3 continuam abertos; grants/contexto,
dispatcher e daemon completos permanecem pendentes.

## Incremento de aplicação de autoridade

O incremento mais recente instala autoridade R4 no runtime Core antes de
prepare/open, renova pelo CAS existente e cerca imediatamente a revogação,
inclusive durante renovação e esperas nativas. Nexus embedded e transporte
Connector consomem essa API com o mesmo wheel `0.2.25.dev0`. O
[relatório de aplicação de leases](M01_LEASE_APPLICATION.md) registra a
campanha e os limites. A emissão canônica de grants no Server, a integração
com o dispatcher/daemon, a recuperação completa e a qualificação final
continuam pendentes. M00/M01 e G0–G3 permanecem abertos.

## Incremento de concessão canônica e recibos

O incremento de [concessão canônica de leases](M06_CANONICAL_LEASES.md) liga
o WSS ao serviço de autorização e à persistência 076, exige aplicação antes
do despacho, consome budget atomicamente e projeta prontidão a partir do
recibo Core de abertura. Passaram 69 testes (56 R4 + 13 grants) e 14 casos
dirigidos com os três aplicativos instalados fora dos clones. Onboarding,
dispatcher/daemon de produto, embedded composto, recuperação e qualificação
continuam pendentes; nenhum marco ou gate foi encerrado.

## Incremento de contenção expirada

O [incremento de contenção expirada](M01_EXPIRED_CONTAINMENT.md) distribui
Core `0.2.26.dev0` aos dois consumidores. Interrupt, close e respostas
estritamente negativas preservam as ações previamente concedidas após
expiração produtiva; revogação e escopo continuam cercados. A coordenação
de controles durante CAS pendente permanece explicitamente incompleta.

## Baseline

- Nexus: `feature/v0.2.0`, HEAD inicial `7ed52c22865a92c3768bc32508ed9e35dc5efdc3`, Python 3.13.1, Windows 11 10.0.26200, `uv.lock` existente.
- Core: HEAD inicial `1560d314ed2b478515dcbbe533436d7d0b027b09`, versão inicial `0.2.10.dev0`, NXL r3. Branch `feature/v0.2.0` criada.
- Connector: HEAD inicial `77fee6d8cde643d4310df5bbc5dfb643c496f677`, versão `0.4.0.dev0`. Branch `feature/v0.2.0` criada.
- O Nexus já tinha 599 exclusões rastreadas em `plans/`, três assets HTTP modificados e arquivos de planejamento R4 não rastreados antes desta implementação. Nenhum reset ou clean foi executado. O Core já tinha o arquivo não rastreado `=1`; ele não foi incluído em commits.

## Incrementos implementados

| ID | Estado | Evidência e limite |
|---|---|---|
| CORE-R4-02/03 | IN_PROGRESS | Core `0.2.11.dev0` gera e valida snapshot de inventário sem path, com revisão SHA-256/JCS completa e ref da instalação; 33 testes de Core passaram. NXL ainda é r3. |
| CORE-R4-02 | IN_PROGRESS | Core `0.2.12.dev0` expõe `discover_installations` sem runtime; o Nexus usa essa fachada para descoberta local. 27 testes direcionados de Core passaram, e `python -I` importou o wheel instalado. SHA-256 `bd5326357608906bdd80ccefc3db4890137d9e8dc00935a88c5f6dd955bf9d8e`. NXL ainda é r3. |
| CON-R4-05 | IN_PROGRESS | Preview do Connector usa a revisão do mesmo Core; função de publicação R4 usa o candidato completo. 18 testes CN4 e 1 novo teste passaram. Publicação HTTP autenticada ainda não foi implementada. |
| NS04.01/04.03 | IN_PROGRESS | Nexus consome catálogo e snapshot do Core sem criar runtime ou depender da aplicação Connector; dois testes locais e teste de protocolo passaram. Persistência e publicação por executor ainda pendentes. |
| NS01.04 | IN_PROGRESS | `GET /v1/connections/protocol` retorna objeto direto com header de revisão e indica NXL R4 indisponível. As demais rotas `/v1` ainda pendentes. 30 testes HTTP existentes passaram. |
| NS01.02/01.03 | IN_PROGRESS | Entrada principal agora é `adapters.inbound.cli.main`, sem ramo MCP stdio. Invocação sem comando mostra ajuda; flags antigas falham sem bootstrap. `serve` continua HTTP. 73 testes de CLI, retenção, tail e paridade passaram. Extra Core fixado, mas lock/instalação limpa ainda pendentes. |
| NS01.01 | IN_PROGRESS | `Deps`/bootstrap em `bootstrap.dependencies`, registro de tools/resources/instructions em `mcp.registration`; HTTP e CLI importam os módulos separados. Quatro testes de extração/paridade e 34 testes direcionados de HTTP passaram. |
| NS00.05 | IN_PROGRESS | Peer sintético com perda de resposta após commit e consulta do mesmo recibo; manifesto classifica provider e dois hosts como NOT_RUN. Cenário NS00.05 passou, mas peers de produto ainda pendentes. |
| NS02.01 | IN_PROGRESS | Chaves imutáveis por Server/executor/binding/sessão/stream/aprovação e geração tipada; teste de colisão entre namespaces passou. Writers persistentes ainda pendentes. |
| NS01.05 | IN_PROGRESS | Comando `admin migrate-mcp-entry` planeja uma entrada explicitamente escolhida, mostra diff sem chave, exige hash revisado para aplicar, cria backup e recusa edição concorrente. Cenário passou. Nenhuma configuração real do operador foi alterada; NS01.04 ainda incompleto. |
| NS02.02/02.03 | IN_PROGRESS | Migração 066 adiciona 20 extensões, FKs/índices, preserva endpoint negado e passa em banco legado; bootstrap mantém server_id/executor local estáveis sem claim. Registro remoto interno é idempotente e vinculado ao ator; rota autenticada e ticket bootstrap ainda pendentes. Três testes NS02 passaram. |
| NS04.01/04.03 | IN_PROGRESS | Catálogo e discovery local vêm do Core sem runtime; ingresso interno valida snapshot completo, escopo do produtor e sequência CAS, mantém duas publicações e não grava paths. Dois testes NS04 passaram. Rota com ticket e UI ainda pendentes. |
| NS02.04 | IN_PROGRESS | Binding lógico interno exige proposta APPLIED com digest do escopo e handle opaco do executor; não resolve path remoto. Repetição do mesmo vínculo preserva ID após expiração da proposta; raiz diferente exige outra aprovação. Validação efetiva da raiz no executor e rota autenticada ainda pendentes. |
| NS03.01 | IN_PROGRESS | `GET /v1/connections/me` reutiliza a identidade bearer autenticada, rejeita hint divergente e retorna DTO direto conforme `MeInfo`. Migração 067 mantém revisões por agente para política, configuração e chave, calculadas de linhas persistidas escopadas. Teste com 100 mil agentes confirmou índice de hash, isolamento, rotação e respostas em inglês sem detalhe interno. A revisão ainda não alimenta a admissão de operações R4. |
| NS02.03/NS03.03 | IN_PROGRESS | `POST /v1/connections/executors:register` usa ator autenticado, intenção idempotente e emite ticket bootstrap aleatório, persistido somente por hash, com audiência e escopos `link:connect`/`inventory:publish`. Retry substitui ticket anterior; outra key, executor, scope, expiração ou epoch são recusados. Emissão vinculada a binding, renovação automática e consumo WSS ainda pendentes. |
| NS04.03/CON-R4-05 | IN_PROGRESS | `PUT /v1/runtime/executors/{id}/inventory` recebe JSON estrito e limitado sob ticket, valida snapshot Core, sequência, produtor e escopo; resposta `InventoryAccepted` direta. Cliente HTTPS Connector consome `/me`, registro e publicação com revisão de header exata. Teste vertical in-process com os dois aplicativos e mesmo Core 0.2.14 passou; provider, processo separado e dois hosts seguem NOT_RUN. |
| NS04.04 | IN_PROGRESS | `GET /v1/runtime/executors/{id}/inventory` e `GET /v1/agents/{id}/runtime-options` devolvem DTOs diretos somente ao agente do executor. Estados técnicos vêm do snapshot Core sem promoção a autorização; flags de bind/start permanecem falsas. Frescor depende de tempo monotônico do processo, expira em 120 s menos idade observada e não é reancorado por replay ou restart. Canal WSS e elegibilidade positiva seguem pendentes. |
| NS04.05/CON-R4-05 | IN_PROGRESS | Nexus e Connector possuem resolução local da seleção pelo helper público do Core após comparar a revisão completa do inventário. Dois binários de mesmo conteúdo continuam instalações distintas mesmo após reorder; ref legada ambígua e drift recusam. Testes locais passaram; helpers ainda não integram o fluxo de apply/prepare nem a prova de frescor do canal. |
| NS02.05/NS06.04 | IN_PROGRESS | Migração 068 guarda frame Core, digest e origem de conexão dos recibos. `POST /v1/runtime/operations/{id}/receipts` exige ticket de binding com `receipt:publish`, operação já admitida e sequência validada pelo reducer do Core; replay idêntico é idempotente. Teste com ticket real e rota HTTP passou. Writers de admissão/outbox e dispatcher ainda pendentes. |
| NS02.05 | IN_PROGRESS | Reader interno de histórico por namespace e sujeito reconstrói e valida recibos do Core após novo bootstrap, sem compor runtime. Teste de isolamento de sujeito e retomada passou. DTO público `OperationView`, admissão e dispatcher ainda pendentes. |
| NS03.03 | IN_PROGRESS | Emissão e verificação de ticket de binding agora seguem o agente do endpoint vinculado, mesmo quando outro agente registrou o executor. A troca do agente no endpoint invalida o ticket antigo. Teste de duas identidades passou; rota pública de emissão/renovação e single-flight ainda pendentes. |
| CON-R4-03 | IN_PROGRESS | Cliente HTTPS Connector valida um recibo Core R4 antes de enviar para a rota própria de recibos com ticket de binding, exige revisão de gerenciamento e confere o ACK exato. Teste com peer sintético passou; daemon ainda não produz/publica recibos por esse caminho. |
| NS06.04/CON-R4-03 | IN_PROGRESS | Teste vertical em processo usa cliente HTTPS Connector e router ASGI Nexus para publicar snapshot Core e recibo Core com ticket de binding real. O teste semeia uma operação admitida; não prova resolve/admit, dispatcher, provider, processo separado ou dois hosts. |
| NS07.01 | IN_PROGRESS | Host técnico embedded no lifespan de `serve`: um journal/runtime Core por sessão selecionada e um ledger de slots compartilhado; abertura fora do loop, inicialização single-flight e waiter cancelado sem cancelar o owner. Sessões do mesmo executor podem ter seleções e callbacks de ambiente distintos. `create_runtime` público compõe o Core diretamente no Nexus; sem seleção aprovada não abre stores. Teste concorrente com Core real passou. Ainda falta ligá-lo à realização, à admissão e ao dispatch; nenhum harness foi iniciado. |
| NS07.02 | IN_PROGRESS | Adapter interno `EmbeddedExecutor` converte open/submit/steer/interrupt/close em DTOs públicos do Core, preserva IDs, contexto e classificações `CoreError`. Teste com Core real e peer nativo sintético atravessa as cinco operações; revisão de configuração obsoleta não chega ao peer. A seleção e o contexto ainda são fornecidos pelo teste, não pelo writer de admissão do Nexus; provider real e UI não qualificados. |
| NS02.05/NS06.04 | IN_PROGRESS | `GET /v1/runtime/operations/{id}` devolve `OperationView` direta ao agente sujeito ou ticket `history:read` vinculado à operação, inclusive antes do primeiro recibo; usa histórico com frame/digest Core validados, recusa outro agente, scope errado e ambiguidade entre executores. Teste HTTP passou. Intent resolve/admit, operador e dispatcher continuam pendentes. |
| NS03.03/CON-R4-03 | IN_PROGRESS | Migração 069 e `POST /v1/connections/bindings/{id}/ticket` emitem credencial de binding ao agente do endpoint com request ID persistido. Replay da solicitação não revela hash como segredo; substituição cita ticket anterior, revoga-o na mesma transação e recusa substituição de ticket já ligado a conexão. Cliente HTTPS Connector tem método R4 tipado; teste vertical agora obtém ticket pela rota antes de publicar recibo. Renovação em daemon, interseção de política de lane e consumo WSS ainda pendentes. |
| NS05.01/CON-R4-05 | IN_PROGRESS | Migração 070 e `POST /v1/runtime/executors/{id}/realizations` recebem claim opaca sob ticket de bootstrap `realization:publish`, conferem candidato/revisão no inventário corrente e escopo do agente, criam workspace lógico sem path e retornam o mesmo mapeamento após replay. Connector agora persiste raiz, candidato completo e refs localmente via StateStore v3, verifica diretório/fingerprint e publica sem path/executável; replay mantém referência e drift de binário recusa. Estado Server segue `PENDING_APPROVAL` até apply; nenhum runtime/outbox nasce na publicação. Ainda faltam consentimento ligado à UI/CLI do host e revalidação imediatamente antes do efeito. |
| NS05.02/05.03 | IN_PROGRESS | Migrações 071/072 e `POST /v1/connections/bindings:prepare`/`:apply` persistem proposta com IDs gerados, diff/escopo e hash aprovado. Prepare compara inventário corrente fresco e realização do agente, é idempotente e não cria endpoint, binding ou outbox; endpoint legado observado bloqueia apply. Apply usa CAS de fonte do agente, revisões, inventário e realização na mesma transação, cria endpoint e binding uma vez, promove vínculo/realização a READY e devolve BindingView recuperável após retry. Teste com mudança de metadata e resposta perdida passou. Ainda faltam aprovação de operador quando política exigir, atualização/rebind e UI. |
| NS06.01 | IN_PROGRESS | `POST /v1/runtime/intents:resolve` persiste ID do cliente, hash do corpo, escopo, semântica e IDs gerados antes de responder; replay idêntico e `GET /v1/runtime/intents/{id}` recuperam a mesma resolução. Preview aceita `runtime.start` explícito e `turn.submit` com sessão; não cria operação/outbox nem chama Core. `can_submit=false` com blocker de execução R4 indisponível enquanto o bundle/host remoto não estiverem qualificados. Teste de isolamento e zero efeito passou. Falta habilitar admissão após autorização completa, reuso e demais ações. |
| NS06.02 | IN_PROGRESS | Migração 073 guarda digest das fontes de autorização no resolve. `POST /v1/runtime/operations` verifica ID/hash/revisão, agente, binding, realização, inventário fresco e sessão/perfil antes de gravar operação, outbox e claim de sessão na mesma transação. Replay retorna a operação existente. O gate público continua fechado porque o Core R4/host remoto não são executáveis; teste sintético isolado provou rollback ao falhar a última gravação e idempotência após commit. Falta qualificação do host, lease/dispatcher e admissão produtiva. |
| NS06.01/06.02 | IN_PROGRESS | Resolve agora calcula blockers de host, realização, inventário, candidato, sessão e perfil e usa a revisão real do perfil; uma fixture sintética qualificada produziu `can_submit=true` e admitiu a operação. Na API de produto, o gate de protocolo continua falso. Testes verificam que inventário obsoleto ou mudança de metadata entre resolve e submit impedem a segunda operação. Ainda faltam reuso de sessão, vínculo de perfil aprovado e demais ações. |
| NS06.03 | IN_PROGRESS | Migração 074 e `reserve_execution_dispatch` fazem reserva durável de item/bytes exatos antes de criar tarefa, em lane de controle independente. `release_unsent_dispatch` aceita somente token/tentativa/classe/custo idênticos ainda em RESERVED; segundo release conflita. `begin_execution_send` revalida fontes do agente, binding, inventário, sessão, perfil e lease ACTIVE após a espera, e faz CAS de RESERVED para SENDING antes de qualquer I/O. Teste sintético confirmou progresso do controle com lane regular saturada, recusa após drift e recusa de release após SENDING. Ainda faltam ownership/recovery de reserva, loop de envio via Embedded/Remote e qualificação do canal; nenhum efeito de produto usa esse módulo. |
| NS06.04 | IN_PROGRESS | Receipt aceito atualiza outbox e `admission_state` na mesma transação: libera bytes reservados, marca DISPATCHED para progresso, RECONCILING para `OUTCOME_UNKNOWN` e RESOLVED_TERMINAL para término. Replay não reaplica a liberação. Teste de sequência Core e consulta após reboot cobre progresso, unknown e resolução posterior. Ainda faltam transporte WSS e reconciliação ativa; nenhum timeout vira retry automático. |
| NS08.01 | IN_PROGRESS | Rota WSS `/v1/runtime/executors/{id}/link` valida transporte TLS (ou loopback estrito), Origin, subprotocolo `nxl.v1`, ticket com audiência/escopo/namespace e revisão Core antes de aceitar ou negociar. A fixture que simula bundle disponível confere `hello`, aloca `connection_id` e geração por CAS, responde `welcome` sem capacidades, aceita apenas heartbeat escopado e libera owner ao desconectar. No produto, o Core ainda anuncia `remote_execution_ready=false` e o upgrade fecha antes de qualquer negociação. O teste cobre ticket ausente/cruzado, Origin/subprotocolo e revisão incompatíveis; ainda faltam expiração/revogação durante canal, attach, reconcile, lease, lanes e envio de operação. Nenhum efeito remoto está habilitado. |
| NS08.02 | IN_PROGRESS | Migração 075 persiste lane por binding/agente/ticket/connection generation. Frame `binding.attach` exige ticket `lane:attach`, escopo e revisões correntes; somente após commit emite `binding.attached` correlacionado. Revogação de ticket, mudança de revisões, geração nova e desconexão fecham a lane por escopo; tentativa A com ticket B ou ticket revogado recebe erro sem derrubar B. Teste de dois agentes e rotação de A passou. Falta attach do Connector real, reconcile/readiness, lease e revalidação na admissão/efeito; o gate de produto continua fechado. |
| NS08.03 | IN_PROGRESS | Após `welcome`, Server envia `reconcile.request` com IDs pendentes do banco e cursor inicial. Erro do journal remoto mantém `RECOVERING`; heartbeat solicita nova tentativa. Apenas report completo e vazio, confirmado contra as operações/sessões persistidas no mesmo CAS, promove `CONTROL_READY` e recebe `reconcile.accepted` sem lanes/leases prontas. Report não vazio mantém recuperação pendente. Teste sintético de falha e recuperação passou; faltam paginação efetiva, merge de receipts/claims/watermarks, Connector real e readiness de sessão. Nenhum efeito remoto foi liberado. |
| CON-R4-03/NS08.03 | IN_PROGRESS | Connector `208a9c9` adiciona cliente WSS R4 separado do transporte R3. Negocia `hello`/`welcome` com Core, valida escopo/geração, espera `reconcile.accepted` correlacionado pelo reducer do Core e mantém o socket disponível ao chamador. Falha ou report vazio para IDs pendentes envia erro e pede nova tentativa; três testes de contrato passaram, além de 27 testes dirigidos do Connector. Ainda não está ligado ao daemon/StateStore, não fornece callback de journal de produto, lanes/leases ou operações. |

O mesmo wheel local `nexus_connector_core-0.2.11.dev0-py3-none-any.whl` foi usado nos testes de consumidor Connector e Nexus: SHA-256 `41193bc203bb6425163b8992effb6dfa701d3ef309ed08832a58d84cc0c3158d`. Importação isolada com `python -I` passou. O artefato não foi publicado em PyPI; os extras `serve`/`serve-lite` do Nexus e a dependência do Connector fixam a versão, mas instalação nova exige disponibilizar esse wheel no índice/ambiente de instalação. O `uv.lock` do Nexus ainda não reflete essa dependência.

Substituição posterior: o wheel `0.2.12.dev0` de hash `bd5326357608906bdd80ccefc3db4890137d9e8dc00935a88c5f6dd955bf9d8e` foi copiado byte a byte para os três repositórios; os pins Nexus/Connector e `uv.lock` do Nexus foram atualizados. Os parágrafos anteriores registram o marco anterior, não o artefato corrente. O NXL segue R3.

`uv lock --check` e `uv sync --extra serve-lite --extra dev --frozen` passaram usando `vendor/wheels` do próprio Nexus. A suíte direcionada NS00/NS01/inventário passou 13 testes no ambiente sincronizado. O ADR em `docs/adr/0001-r4-authority-and-wire.md` registra responsabilidades, representação direta `/v1` e invariantes de efeitos; NS00.03/04 exercitam separação do envelope legado e rejeição R3/R4, inclusive receipt histórico R3. Nenhum desses resultados qualifica o dispatcher remoto.

O Core tem no commit `c67487e` um preview de codec NXL R4 em wheel `0.2.13.dev0`, mas `R4_BUNDLE_EXECUTABLE=False` e a revisão negociável continua R3. O Nexus/Connector ainda instalam `0.2.12.dev0`; não promover o preview a gate remoto. A suíte NS01/NS02/retenção passou 38 testes depois da migração 066.

Atualização: Nexus e Connector agora fixam e vendorizam o mesmo wheel Core `0.2.13.dev0`, SHA-256 `be0d974b036d6384e69655cff5556d6f5ee853f991a913087fe947c56fa2be96`. O `uv.lock` do Nexus aponta para esse wheel local; `uv lock --check`, `uv sync --extra serve-lite --extra dev --frozen` e 22 testes direcionados de Nexus passaram. O Connector passou oito testes de catálogo e inventário consumindo o wheel R4 parcial. A revisão negociável permanece R3 e `remote_execution_ready=false`; este marco não habilita efeito remoto.

Atualização seguinte: Core `0.2.14.dev0` (commit `c78daf5`, SHA-256 do wheel `759cdee946037ed5e215f901cdfb09b31baf350c7fde69e4d5f79bd41f515bee`) inclui payloads fechados de decisão/input, consulta e recibo com escopo de conexão e adapter IDs gerados do registry. Os 15 testes do codec passaram; importação `python -I` do wheel confirmou `development-partial` e `executable=False`. Nexus e Connector consumiram o mesmo wheel: 22 e oito testes direcionados passaram, respectivamente; `uv lock --check` e `uv sync --extra serve-lite --extra dev --frozen` passaram no Nexus. Ainda não há reducers nem qualificação de efeito remoto, portanto a revisão negociável permanece R3.

O wheel Nexus recompilado contém `066_execution_r4_expand.sql`; instalado em ambiente separado e iniciado com `python -I`, aplicou até a revisão 66 e persistiu os IDs de instalação. A validação foi feita em banco temporário, sem aplicar migração no banco do operador.

Atualização Core `0.2.15.dev0` (commit `941d813`, SHA-256 `4caa45add41da1fbc409316b90c34beafd60e3ea8a752c866071616af50f152a`): reducers puros de lease correlacionada e recibo de operação, com 19 testes direcionados. O ACK de aplicação continua distinto da concessão; o host ainda não instala `ExecutionContext` nem executa efeito remoto via R4. Nexus e Connector fixam o mesmo wheel; `uv lock --check`, `uv sync --frozen`, 14 testes do cliente Connector e o teste vertical de inventário passaram. O bundle continua `development-partial`, sem anúncio R4 como executável.

Atualização Core `0.2.16.dev0` (commit `4721bf4`, SHA-256 `19b28e7f8f20c02032c32cd6b47f7d9e5b7f3b5b503c3e17620cc8ba6ee17946`): reducers puros correlacionam ACKs `binding.attached` e `reconcile.accepted` com tentativa, conexão e geração; vencimento usa o instante monotônico anterior ao envio. Vinte testes direcionados passaram. Canal/lane prontos continuam separados da lease Core e de efeito nativo. O bundle ainda é `development-partial` e a revisão R4 não é anunciada como executável.

Atualização Core `0.2.17.dev0` (commit `af2534a`, SHA-256 `c35526cb347df56388ffae3fb3c3daf34745b8d48f01ff82c8116112409b7f`): schema fechado para 21 tipos de frame, incluindo handshake, attach, reconcile, eventos, notificações de aprovação e encerramento. Reducers de watermark de eventos e correlação de aprovação são puros; 24 testes direcionados passaram. A execução R4 permanece desabilitada até implementação e qualificação dos hosts, dispatcher, lease aplicada e provider.

Atualização Core `0.2.18.dev0` (commit `da47d79`, SHA-256 `547ab7dfde09adff79f38f5cdf688e5b9d0d7ed3caddf4de445766afdefde0da`): projeção pura verifica um recibo `turn.submit` do journal Core antes de gerar o frame R4 com hash de wire distinto. Divergência de texto, escopo ou ID é recusada. Vinte e cinco testes direcionados passaram. `runtime.open`, demais ações e host remoto ainda precisam de projeções e qualificação; bundle continua `development-partial`.

O cliente HTTPS do Connector agora chama a projeção Core antes de publicar um recibo de turno. O teste vertical Nexus–Connector usa intenção R4 e recibo Core sintéticos com hashes de domínios distintos, depois consulta o ACK do Nexus. Continua sem admissão real, daemon, provider ou dois hosts.

O teste vertical passou a compor o Core real no lado do executor, abrir uma sessão com peer nativo sintético e enviar um `turn.submit` antes da projeção/publicação. O Nexus persiste `SUBMITTED` e o cliente consulta a mesma `OperationView`. A operação e o binding ainda são semeados no banco; não é prova de daemon remoto, provider real ou dois hosts.

Atualização Core `0.2.19.dev0` (commit `cf15b02`, SHA-256 `3b1b334f61f8ad5a2a59c63dcd127ced26a9d426dde7bff68085e4081d01c072`): falhas de projeção depois de um recibo Core agora preservam `possible_effect=true` e `retry_safe=false`, inclusive em escopo, payload e schema divergentes. Vinte e cinco testes direcionados passaram. O wheel anterior fica apenas para rastreabilidade.

Atualização Core `0.2.20.dev0` (SHA-256 `7e9addcb72c52aefe35ea136b4c706721b104f6f9ce4a804a0071d2e829ec4c1`): projeção verificada de `turn.steer` compara texto, escopo e `expected_turn_id` com o hash do journal Core antes de produzir o hash R4. O cliente HTTPS do Connector publica esse recibo; o teste vertical em processo executou submit e steer no Core com peer sintético, publicou ambos no Nexus e consultou as duas operações. Binding/operações continuam semeados; não prova daemon, provider ou dois hosts. `turn.interrupt` e `runtime.close` ainda precisam alinhar o `reason` exigido pelo wire R4 com a semântica do Core.

Atualização Core `0.2.21.dev0` (SHA-256 `6cf55425acc44b4ead9bfd1abd6e216d2c9ed00c7e137d76800b1a42f2f065ed`): `turn.interrupt` e `runtime.close` incluem `reason` opcional no hash do journal; chamadas legadas sem reason continuam válidas. As projeções R4 exigem e conferem o reason antes de publicar. O teste vertical em processo agora executa e publica submit, steer, interrupt e close do Core pelo cliente Connector, consulta quatro `OperationView` no Nexus e verifica o adapter embedded. Binding e operações seguem semeados; não há admissão/dispatcher de produto, provider real, daemon ou dois hosts.

Atualização Core `0.2.22.dev0` (SHA-256 `a909fab422f506c9631ef1ed57cea4ec09d235bc44f9e92ab1f84b4e289e02db`): `project_r4_open_receipt` confere candidato local, adapter, modo, contexto, `PreparedLaunch`, stream epoch e hash do journal antes de produzir o recibo wire. O cliente Connector o publica e o teste vertical agora abre a sessão com Core real e publica open, submit, steer, interrupt e close pelo Nexus. Core 29 testes, Connector 24 e teste vertical três cenários passaram com o mesmo wheel; `uv lock --check` e sync frozen passaram. Operações seguem semeadas no teste e o bundle continua `R4_BUNDLE_EXECUTABLE=False`.

O teste vertical subsequente passou a validar a raiz e o candidato no Connector, persistir o registro local, publicar uma realização opaca e executar prepare/apply reais pela rota do Nexus. Endpoint, binding e revisões do agente vêm do Server; somente operações admitidas ainda são semeadas. O identificador de consentimento é fornecido pela fixture; não há fluxo de consentimento da UI/CLI, dispatcher ou autorização de efeito de produto.

O cliente Connector agora também consulta `intents:resolve` depois de apply no teste vertical. A resolução é durável e bloqueada (`can_submit=false`); a fixture continua executando as operações Core separadamente, sem despachá-las a partir dessa resolução.

O cliente HTTPS do Connector passou a enviar a tupla exata `client_intent_id`/`operation_id`/`resolution_revision`/`intent_hash` para `POST /v1/runtime/operations`, após verificar `can_submit` e blockers. A resposta é conferida contra escopo, ação e hash da resolução; retorno divergente preserva possível efeito e exige consulta. O teste vertical confirma que a resolução bloqueada não gera requisição de admissão. O método legado de submit e o daemon ainda não usam esse fluxo R4.

## Gates

G0, G1, G2 e G3 permanecem abertos. Nenhum teste acima prova provider real, efeito remoto ou multi-host. O endpoint de protocolo anuncia `nxl_accepted=[]` e `remote_execution_ready=false` enquanto o bundle R4 não existir. Não executar efeitos remotos com r3.

O pacote completo em `plans/` foi disponibilizado durante a execução. `python plans/validar_pacote.py` passou oito verificações documentais; `tests/execution_r4/test_ns00.py` passou os dois cenários de baseline e crosswalk. Essa validação não prova capacidade de produto. As demais tarefas seguem a especificação e nenhuma é marcada DONE por um recorte parcial.

Um wheel do Nexus foi instalado com o extra `serve-lite` num ambiente isolado com o wheel Core local; `python -I` importou ambos de `site-packages`, mostrou o help e serviu `/v1/connections/protocol` com `remote_execution_ready=false`. O teste não substitui a atualização do lock nem o bundle NXL R4.

## Approved launch configuration — 2026-09-30

Connector commit `4447adc3700b3d700fab2458fdebeb46b52be0e1` adds schema 8 and the default digest-bound launch port. Installed verification: Connector 305 passed / one skipped; Nexus 73 passed. Core remains 0.2.30.dev0 with the same shared hash. See [evidence](test_runs_20260930_approved_launch.json). Automatic tool composition, public configuration capture and daemon adoption remain pending under M02/P6.1/M06; no gate closed.

## Approved Pi native tools — 2026-09-30

Connector `f1714f4f392c3ed7d41b14be8151d5af6a4669d9` composes durable Pi capabilities with approved configuration through the R4 owner. Installed tests: Connector 310 passed / one skipped; Nexus 77 passed, including actual technical Pi child execution and retained shutdown producers. See [evidence](test_runs_20260930_approved_native.json). Core remains unchanged. Automatic boot adoption, MCP composition and complete provider/platform acceptance remain pending; no gate closed.

## Approved MCP session configuration — 2026-09-30

Connector `45c37e60e9546205b042544a706c27c160eb94dc` composes Codex/Claude direct HTTP configuration from approved references and durable capabilities. Installed verification: Connector 328 passed / one skipped; Nexus 78 passed, including canonical identity, claim and completion using the generated environment. See [evidence](test_runs_20260930_approved_mcp.json). The initial boundary-test false positive is retained with the AST correction. Core is unchanged. Automatic daemon boot, native-login migration, lifecycle recovery and final provider/platform acceptance remain pending; no gate closed.
