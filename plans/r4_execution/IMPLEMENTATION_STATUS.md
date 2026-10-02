 # Execução R4 — estado verificado em 2026-10-02

## Current acceptance reconciliation: executable Core .55

The .55 same-machine Pi buffer diagnostic passed with unchanged installed bytes:
peak queue 64 events / 49,045 serialized bytes, no queue/history refusal, three
native actions and successful turn/close/cleanup. This did not reproduce or solve
the earlier stream loss. The preceding instrumented pass lacked its detailed
report and is retained with that limitation. See [diagnostic evidence](M13_PI_STREAM_DIAGNOSTIC.md).
Core hosted .55 completed all six OS/Python cells with only the same stale-doc
version failure; Core `9a19ebe` corrects it and `10585bb` retains Windows/Linux
installed documentation evidence. New hosted qualification remains pending.

Core `beed295` removes identical overlapping PATH/explicit Pi candidates while
refusing conflicting observations of the same reference. Connector `7cf54e1`
pins that wheel. Nexus installed discovery, inventory, daemon and refresh checks
passed 21 cases on each of Windows and WSL Linux, with unchanged campaign inputs.
The preceding .54 real Codex CLI cycle passed; its Pi attempt failed control
publication. With .55, Pi passed publication but one native turn lost its event
stream. A later instrumented cycle passed without an application change; the
intermittent observation loss remains unresolved. See
[same-machine .55 evidence and exact artifacts](M13_SAME_MACHINE_055.md).
These development results do not freeze the final tuple or close any gate.

Acceptance topology: by explicit user direction, continue testing on this machine
with separate local/remote processes and environments. Cross-machine acceptance
is reserved for a later manual session with the user; it remains pending and must
not be inferred from same-machine results.

The .54 installed Claude remote CLI journey now passes on this Windows machine:
actual HTTP/WSS, real provider, lease renewal, three native decisions, completed
handoff, successful close and zero-exit cleanup with campaign credentials removed.
The initial missing-keyring environment refusal is retained. See
[same-machine native evidence](M13_SAME_MACHINE_054.md). Other providers and the
remaining full acceptance scope are still open.

Core `1c7cf79` fixes the reproduced zero-candidate defect: unapproved PATH
installations remain visible and untrusted, including the Windows Codex npm and
managed Pi layouts. Connector `07e78f2` adopts the same shared discovery facade.
A fresh installed Windows CLI found all three real providers in 13.50 seconds
without launching them. Nexus adopted the exact .54 wheel and passed 57 installed
integration checks on each of Windows and WSL Linux with unchanged inputs.
The initial failed adoption and the corrected artifacts are retained in
[discovery presence evidence](M03_DISCOVERY_PRESENCE.md). These passes do not close
the full provider/host matrix, NS15.05, M13 or any release gate.

Connector audit A10 now exercises the current R4 daemon/selection/capability
and real Core environment renderer instead of skipping a legacy startup refusal.
Seventy installed audit/daemon/capability checks passed without skips on each of
Windows Python 3.13.1 and WSL Linux Python 3.12.13. The native peer is synthetic;
this closes that positive-control coverage gap, not provider or independent-host
acceptance. See Connector `plans/implementation/AUDIT_R4_ENVIRONMENT.md`.
Its sole open issue remains macOS containment (#1); documentation/diagnostic
corrections do not constitute native macOS support. All release gates remain open.

Installed campaigns now freeze frontend/build/runner inputs too: the Windows and
Linux checks each recorded 77 frontend files and no mutations. Connector `beead27`
reproduced the two renewal-entry scheduling failures as LEASE_EXPIRED, corrected
the synthetic clock tests and retained actual expiry refusal. Its complete
installed Windows suite passed 716 tests with two skips; Linux passed 710 with
six skips, then its two packaging setup errors passed after installing the
declared missing build dependency. Subsequent directed observer/boundary checks
passed on both. Hosted event-recovery timeout and final qualification remain open.
See [campaign guard and current regression evidence](M13_CAMPAIGN_INPUTS.md).

The dashboard can now request and observe passive host refresh, retaining the
same intent across lost replies, host switches and tab reload. A packaged Edge
case passed after a test-only theme-logo selector correction; nine companion
regressions passed in the initial installed campaign. Exact reports and the
reviewed screenshot are in [the refresh ledger](M10_INVENTORY_REFRESH.md).
This qualifies that Windows UI flow with synthetic discovery and a real API
bridge, not the full onboarding/provider/platform matrix or final delivery.

Passive inventory refresh now connects the durable scoped queue to public HTTP,
the embedded consumer and Connector `c110246` through an explicitly negotiated
HTTP extension. Only a correlated publication completes a claimed request. Each
of Windows/Python 3.13.1 and WSL Linux/Python 3.12.13 passed 26 installed Nexus and
79 Connector checks; the actual daemon completed offline/startup and online
requests over HTTP/WSS/IPC on one host. Independent-host acceptance remains
open. The preceding Connector hosted run at `d2e240e` has two Windows/Python 3.13
renewal-entry timeouts; directed passes do not close that finding. See
[implementation, artifacts and remaining work](M10_INVENTORY_REFRESH.md).

Connector `d2e240eb21c6a40523d2a5bb585cc0b44285c4b8` isolates cleanup-ordering
acceptance from its synthetic lease clock: a delayed event loop reproduced the
pre-renewal timeout, then both normal/delayed cases passed with the shared public
Core clock. A separate expiry case refuses another renewal request. The same 59
installed cases passed on Windows and WSL Linux; after adding failure-observer
diagnostics, 43 overlapping cases passed on each. Product/package bytes and
three-second observation limits are unchanged. The exact hosted cause and four
other Connector timeouts remain unconfirmed. See the
[Connector report](https://github.com/OktoLabsAI/okto-nexus-connector/blob/d2e240eb21c6a40523d2a5bb585cc0b44285c4b8/plans/implementation/CI_RENEWAL_SCHEDULING.md).

Writer admission now rechecks its deadline after notification, before taking a
free slot. Two controlled-clock cases failed before and pass after the fix;
29 installed checks passed on each of Windows/Python 3.13.1 and WSL Linux/Python
3.12.13 with unchanged inputs. This development artifact has not repeated the
full load/hosted acceptance. See [deadline race and evidence](M13_WRITER_DEADLINE.md).

SQLite writers now enter a FIFO queue within their connection factory, sharing
the existing timeout with SQLite and preserving read snapshots and no replay.
Installed Linux regression passed 42 checks. Final load/docs/vault/lease campaigns
passed 24 checks on Windows and 23 with one platform skip on Linux. The load
fixture now checks actual executor-pool bounds and maintains real inventory and
lease authority over HTTP/WSS. NS15.05 no longer consumes pytest arguments or
overwrites the default evidence artifact from its test. Full hosted and
independent-host acceptance remain open; see [scope and artifacts](M13_WRITER_FAIRNESS.md).

Two installed Linux/Python 3.12.13 NS14.04 runs failed the unchanged thread-growth
assertion. Identity transactions stayed below 228 ms; the instrumented run added
11 default asyncio pool threads while named Nexus workers stayed unchanged.
Background storage failures remain unresolved. No application behavior or test
limit changed. See [measurements and failed campaigns](M13_CI_LINUX_LOAD_DIAGNOSIS.md).

Heartbeat storage failures now explicitly close the accepted control link without
retry or private diagnostics, then follow existing scoped cleanup. A fresh Nexus
development wheel passed 19 installed checks with unchanged inputs. This fixes
the uncaught-error path, not NS14 writer starvation; persistent-store cleanup and
hosted acceptance remain open. See [failure scope and artifacts](M13_LINK_STORAGE_FAILURE.md).

Capture/projection isolation now separates progress from throughput and queue
overflow. Three installed checks passed, including real fsync with delayed storage
and the unchanged overflow/unknown-result negative case. No application behavior
changed; the historical CI occurrence still needs hosted confirmation. See
[scope and measurements](M13_CI_CAPTURE_PROGRESS.md).

Connector `37726bd5657e9961e9d14a77e035993d9f118e5f` removes checkout injection
from the CLI E2E subprocesses: three scenarios passed with isolated installed CLI
and daemon processes. The preceding full suite passed 699 tests with two skips,
but still used source paths in those CLI children; that limitation is recorded.
Fifty-four affected discovery/control checks passed after adding public daemon
status to timeout diagnostics. Two hosted Windows timeouts remain unreproduced
and unresolved. Application bytes and pinned wheels are unchanged. See the
[Connector report and evidence](https://github.com/OktoLabsAI/okto-nexus-connector/blob/37726bd5657e9961e9d14a77e035993d9f118e5f/plans/implementation/CI_DISCOVERY_RECHECK.md).

The NS14 load fixture now republishes a newly observed inventory through its
reconciled channel; the technical Pi test observes shutdown completion before
checking its listener. Six installed checks passed with unchanged inputs.
Linux contention, Windows capture and a newly inspected Connector CI timeout
remain unresolved. See [Windows CI follow-up](M13_CI_LOAD_REFRESH.md).

Boot-budget accounting now has deterministic coverage, with independent real-thread
stuck-slot checks retained. Fourteen installed tests passed with unchanged inputs.
Historical CI is terminal and Windows findings still require diagnosis; no release
gate is closed. See [budget scope and remaining findings](M13_CI_BOOT_BUDGET.md).

Embedded execution, renewal and maintenance now preserve the first failure instead
of replacing its diagnostic during containment. A new development wheel passed 48
installed checks with unchanged inputs, including vault refusal and shutdown recovery.
Hosted confirmation and NS14 contention remain pending. The boot-budget fixture
is addressed above. See [failure-cause evidence and CI queue reconciliation](M13_CI_FAILURE_CAUSE.md).

Native factory cutover and canonical session reuse passed 42 installed checks
with unchanged inputs. Production tests now assert migration refusal for retired
constructors; public R4 tests cover concurrent start admission and sibling lifecycle
using actual protocol readiness. Linux/Python 3.11 revealed two additional historical
CI failures requiring diagnosis. See [scope and evidence](M13_CI_FACTORY_CUTOVER.md).

Seven positive-stdio CI findings are now covered through an independent MCP HTTP
client or an explicit test-only store writer. Eighteen installed checks passed in
a fresh environment with unchanged inputs; no product transport was restored.
See [HTTP client and writer scope](M13_CI_HTTP_CLIENTS.md). Native factory migration,
load contention, complete current regression and release acceptance remain open.

Trust and retained recovery follow-up passed 46 installed tests across two
unchanged-input campaigns. The missing fixture admission fence, constructor-time
revocation expectation and retired-stdio handoff recovery test are corrected.
The historical Linux/Python 3.13 job failed 42 tests; the NS14 contention difference
between Python cells remains unresolved. See [scope](M13_CI_TRUST_RECOVERY.md).

MCP surface 64 now documents all harness parameters and both message workspace
selectors. Installed CI corrections passed 59 tests with one existing manual skip
and unchanged inputs. Hosted checkout, marker preservation, migration and historical
surface assertions were corrected; the full CI failure and remaining runtime/trust
findings remain open. See [corrections and evidence](M13_CI_SURFACE_REPAIR.md).

The dashboard now reviews/applies a unique host-published preparation and reuses
its approved binding. Eighteen corrected installed checks passed, including
response-loss recovery with the same request and refusal before unrecorded writes.
First-use embedded preparation and runtime operations remain pending. The full
Linux/Python 3.12 CI cell at `0e9274b` also completed with 43 failures and one error;
these regressions require investigation before release. See
[consent scope and CI findings](M10_BINDING_CONSENT.md).

The dashboard now provides explicit R4 executor/installation/workspace selection
using current scoped API facts. Twenty-four installed checks passed, including
real Edge with packaged assets, reference-preserving reorder and stale/revoked
selection invalidation. The consent follow-up is described above; runtime operations
remain pending. See
[selection scope and remaining NS13 work](M10_RUNTIME_SELECTION.md).

MCP identity resource v30 / surface 63 now describes current R4 onboarding and
controls, removes obsolete provider-version claims and scopes retained legacy
maintenance. Twenty-three installed resource/surface/OpenAPI checks passed with
unchanged inputs. The NS15.05 ledger review also confirms TN-38/39/40 already have
historical scoped passes; final-artifact regression and dashboard acceptance remain
open. See [MCP and ledger reconciliation](M12_NS15_05_MCP_RECONCILIATION.md).

NS15.05 operational reconciliation now removes stale R3/legacy guidance and
verifies the actual R4 bundle in Connector doctor. Eight installed tests, 34
Connector command examples and the Nexus guide's seven help commands/14 routes
passed. See [scope and remaining scenario work](M12_NS15_05_OPERATIONAL_RECONCILIATION.md).
This is supporting documentation evidence, not full NS15.05 or gate closure.

Connector `8ff791c` adds explicit, byte-bound installation observation. Real
installed CLI probes passed for Codex 0.159.0 and Claude 2.1.282; 54 installed Nexus
integration tests passed with unchanged inputs. The full Connector run retained
693 passes, two skips and two missing-build-dependency errors; both packaging
cases subsequently passed in a clean environment. See
[observation scope and evidence](M03_INSTALLATION_OBSERVATION.md). Connector
documentation follow-up `e235e3b` removes the legacy quickstart. Embedded
qualification and full browser onboarding remain pending.

The binding-read route and operator inventory/runtime-options scope are now
implemented; see [canonical reads](M10_BINDING_INVENTORY_READS.md). Current
replacement/revocation facts are projected without provider access or execution.
Installed verification passed 37 tests with unchanged campaign inputs.
The earlier route-audit finding remains historical evidence. Workspace-aware
eligibility now combines Core facts with current policy; 35 installed tests passed
with unchanged inputs. See [runtime options](M10_RUNTIME_OPTIONS.md) for scope and
remaining public qualification/delegation gaps. Inventory refresh remains pending.

Core `3a1e884` and Connector `4724cc6` passed their complete six-cell hosted
Windows/Linux Python 3.11–3.13 matrices. Installed directed Nexus R4 checks
passed 38 cases on both Windows and WSL Linux. Six real Windows provider/mode
journeys passed without readiness overrides; their exact scope and limitations
are recorded in [native evidence](evidence/native-053-acceptance/README.md).

The complete immutable-input Nexus R4 regression finished with 708 passed,
6 failed, 2 setup errors and 6 opt-in skips. All monitored inputs were unchanged.
The failures exposed stale pre-promotion expectations and fixtures competing
with the now-active dispatcher. Corrections passed 25 source-level directed
tests. A fresh wheel installation then passed all 26 directed cases (including
packaged OpenAPI) in 109.76 seconds with unchanged campaign inputs and compatible
dependencies; see [installed corrections](evidence/r4-053-installed-corrections/campaign.json).
The original failure is retained in
[full regression evidence](evidence/r4-053-full/campaign.json).

Actual packaged-browser inspection confirms M10/NS13 remains incomplete:
legacy setup UI, duplicated adapter labels and untranslated graph text.
The inventory-refresh route and complete public qualification/delegation journey
still need completion. OpenAPI's packaged FileResponse annotation
failure has a code fix and a regression test. See the
[acceptance audit](evidence/acceptance-audit-053.md). Final artifact freeze,
complete Nexus regression, UI/CLI/fault/platform and independent-host acceptance
remain open. Historical sections below retain their original revision scope;
they do not override this current status. No G0–G3 gate is closed.

## M13 Core 0.2.52 consumer qualification in progress

Both consumers now pin the same Core lease-boundary fix. Nexus clean boot without Connector/Torch and 27 installed dispatch/bootstrap/import checks passed; Connector installed integration/CLI checks passed 8 tests. Dashboard, wheel and sdist were rebuilt in an isolated source copy. See [M13 reconciliation](M13_CI_RECONCILIATION.md) and [artifact evidence](evidence/m13-core052.json). Full regressions, hosted Windows checks, real providers, UI and independent-host acceptance remain open; no gate is promoted.

## TN-40 supported rollback - October 1, 2026

**TN-40 PASSED** at legacy_acceptance. The installed recovery campaign passed **3 tests**, including both NS15.04 regressions. Nonempty versioned policies/pinned bindings, public permissions/revisions, migration records and uncertain execution history survive same-version snapshot recovery after real backfill and Core dispatch with a synthetic peer. Unsafe restore/overwrite and missing journals are refused without replay. See [scope](M12_TN40_ROLLBACK.md) and [manifest](test_runs_20261001_tn40.json). NS15.05's four scenarios now have passing evidence; task dependencies and M13/G0–G3 remain open.

## NS15.05 documentation and identity/cache acceptance - October 1, 2026

**TR4-15-05, TN-38 and TN-39 PASSED** at their declared layers. Installed campaign: **55 distinct passes and 3 architecture checks**. Normative documentation checks cover real CLI help/routes, Core IDs and rebuilt dashboard assets. Public scoped authentication among 100,000 Agents, indexed 100,000-key churn, bounded memory, unchanged thread count, invalidation races and credential epoch rotation reuse existing tests. See [crosswalk and limitations](M12_NS15_05_ACCEPTANCE.md) and [manifest](test_runs_20261001_ns15_05.json). TN-40, dependency acceptance and final G0–G3 remain open. This supersedes the earlier NS15.05 partial documentation note; final release README metadata still requires the M13 rebuild.

## NS15.05 documentation cutover - October 1, 2026

Current R4 operations and evidence entry points replace obsolete stdio/legacy-open guidance. MCP resource identity v29 and surface revision 62 expose updated authentication instructions; dashboard source help reflects HTTP MCP. Supporting checks: seven installed CLI help commands, thirteen installed route declarations and **26 source regression passes**. See [scope and remaining work](M12_NS15_05_DOCUMENTATION.md). TR4-15-05 and TN-38/39/40 remain NOT_RUN; packaged dashboard and final artifact qualification remain required.

Entries below are a chronological evidence history. Their remaining-work statements describe their own capture time; later entries supersede resolved items. The acceptance inventory remains authoritative for scenario acceptance.

## NS15.04 configuration and post-effect restore - October 1, 2026

**TR4-15-04 PASSED at migration**, configuration and restore cases. Installed campaign: **14 distinct passes and 3 architecture checks**. TR4-15-04 passed at migration: atomic selected configuration retry, foreign-owner refusal, and joint offline restore of Nexus/Core journals and session config after a possible native effect. RECONCILING history and no-retry facts are preserved; unsafe restore/overwrite and missing Core journals are refused. See [scope](M12_NS15_04_CONFIG_RESTORE.md) and [manifest](test_runs_20261001_ns15_04.json). Task dependency acceptance and final M13 provider/platform/multi-host/release gates remain open.

## NS15.03 physical helper removal and normative acceptance - October 1, 2026

**TR4-15-03 PASSED at unit_contract**, REST and MCP. Installed campaign: **98 distinct passes and 3 architecture checks**, 11 skips. TR4-15-03 passed in both REST and MCP cases. Retired process ownership, framing, event buffers and version probes are absent from the Server package; only inert legacy metadata and redaction error identities remain. Core owns physical native runtime. See [scope](M12_NS15_03_HELPER_REMOVAL.md) and [manifest](test_runs_20261001_ns15_03_helper_removal.json). Task dependency acceptance, NS15.04 configuration/restore and final provider/platform/release gates remain open.

## NS15.03 native implementation removal - October 1, 2026

Installed verification: **449 distinct passes and 3 architecture checks**, with **81 skips (72 platform, 9 opt-in live-provider)**. The four duplicate native connector implementations are absent from the Server source/package and installed wheel. Historical domain regression tests explicitly inject test-only fixtures; production execution remains in Core. See [scope](M12_NS15_03_NATIVE_REMOVAL.md) and [manifest](test_runs_20261001_ns15_03_native_removal.json). Shared native process/framing helper separation, canonical-attempt policy, normative TR4-15-03, NS15.04 configuration/restore and final provider/platform/release gates remain pending.

## NS15.03 production loader cutover - October 1, 2026

Installed verification: **86 product passes and 3 architecture checks**. Production Server composition no longer imports or constructs the four duplicate native connectors. Default legacy factories require canonical binding migration; canonical callers execute through Core. See [scope](M12_NS15_03_LOADER_CUTOVER.md) and [manifest](test_runs_20261001_ns15_03_loader_cutover.json). Physical duplicate-code removal, canonical-attempt re-selection policy, full restore and final provider/platform/release acceptance remain pending.

## NS15.03 legacy-to-canonical fallback - October 1, 2026

Installed verification: **44 product passes and 3 architecture checks**. Typed legacy pre-write proof can transfer the same approved conversational claim into atomic R4 admission at the persisted retry deadline. No canonical target enters a legacy worker. Revocation and failed admission roll back; uncertain effects never transfer. See [scope](M12_NS15_03_FALLBACK.md) and [manifest](test_runs_20261001_ns15_03_fallback.json). Canonical-attempt re-selection, native loader removal, full restore and final provider/platform/release acceptance remain pending.

## NS15.03 capture retention and subscriber parity - October 1, 2026

Installed verification: **21 product passes and 3 architecture checks**. Core compacts only Server-committed events; old Core cursors report EVENT_GAP. Server retention preserves canonical result provenance and authorized history. Legacy subscriber registry has no production consumers to migrate. See [scope](M12_NS15_03_RETENTION.md) and [manifest](test_runs_20261001_ns15_03_retention.json). Cross-protocol fallback, native loader removal, full restore and final provider/platform/release acceptance remain pending.

## NS15.03 canonical domain recovery - October 1, 2026

Installed verification: **32 product passes and 3 architecture checks**. Domain maintenance preserves the canonical send fence and requires confirmed canonical session closure before explicit uncertain-claim takeover. Detail inspection exposes scoped canonical references. See [scope](M12_NS15_03_RECOVERY.md) and [manifest](test_runs_20261001_ns15_03_recovery.json). Capture retention, subscriber parity audit, cross-protocol fallback, native loader removal and final restore/release acceptance remain pending.

## TR4-06-05 combined consumption - October 1, 2026

**Normative domain_integration scenario PASSED** in five cases; installed campaign: **6 product passes and 3 architecture checks**. Both live canonical executors share one logical delivery/claim; priority selects one native effect and excludes MCP pull. Observer never executes, native terminal does not complete handoff, concurrent handoff claims retain one winner. See [scope](M12_NS06_05_COMBINED.md) and [manifest](test_runs_20261001_ns06_05_combined.json). Task dependencies, remaining NS15.03 migration, final restore and release gates remain open.

## NS06.05 canonical consumption - October 1, 2026

Installed verification: **7 distinct product passes**, plus **3 architecture checks**. MCP pull exclusion for embedded and automatic remote domain delivery; sequential and concurrent pull/managed handoff claims preserve one winner and grant budget. See [scope](M12_NS06_05_CONSUMPTION.md) and [manifest](test_runs_20261001_ns06_05_consumption.json). Combined local/remote endpoint competition on one delivery, final normative TR4-06-05 acceptance and release gates remain open.

## NS15.03 canonical event reads - October 1, 2026

Installed verification: **78 distinct product passes**, plus **3 architecture checks**. Canonical MCP/REST event reads share session authority and contiguous persisted history, with scoped pagination, integrity checks and closed-session replay. See [scope](M12_NS15_03_EVENT_VIEWS.md) and [manifest](test_runs_20261001_ns15_03_event_views.json). Combined claim competition, context-only observation, remaining subscriber parity audit, cross-protocol fallback, capture retention, native loader removal and final restore/release acceptance remain pending. TR4-15-03 remains NOT_RUN.

## NS15.03 canonical result publication - October 1, 2026

Installed verification: **116 distinct product passes**, plus **3 architecture checks**. Canonical results now reuse governed message publication, HITL, private artifacts and explicitly admitted structured handoff decisions. Schema 096 preserves legacy result IDs and dependent references with checked atomic reconstruction. See [scope](M12_NS15_03_PUBLICATION.md) and [manifest](test_runs_20261001_ns15_03_publication.json). Combined claim competition, context-only observation, runtime-event projection, cross-protocol fallback, canonical capture retention and native loader removal remain pending; normative acceptance/release gates stay open.

## NS15.03 canonical result capture - October 1, 2026

Installed verification: **73 distinct product passes**, plus **3 architecture checks**. Schema 095 materializes bounded canonical output with contiguous authenticated event provenance, atomic ACK rollback and replay protection. Authorized operation history exposes terminal output without legacy harness rows. See [scope](M12_NS15_03_RESULTS.md) and [manifest](test_runs_20261001_ns15_03_results.json). Publication, structured work decisions, result artifacts/retention, combined claim competition, cross-protocol fallback and native loader removal remain pending; normative acceptance/release gates stay open.

## NS15.03 logical handoff workspace - October 1, 2026

Installed verification: **334 distinct product passes**, plus **3 architecture checks**. Public MCP handoffs and HTTP callers now use existing logical workspaces without Server-local paths, preserving claim, capability and approval authority. See [scope](M12_NS15_03_HANDOFF_WORKSPACE.md) and [manifest](test_runs_20261001_ns15_03_handoff_workspace.json). Combined claim competition, canonical structured results, result/event publication, cross-protocol fallback and native loader removal remain pending; normative acceptance/release gates stay open.

## NS15.03 canonical managed handoff - October 1, 2026

Installed verification: **111 distinct passes**, plus **3 architecture checks**. Managed claims atomically retain work grants, exclusive delivery and canonical opening/turn admission. Claim/grant authority is revalidated before effects; native terminal does not complete the handoff. Authorized history exposes canonical operation/session references. See [scope](M12_NS15_03_HANDOFF.md) and [manifest](test_runs_20261001_ns15_03_handoff.json). Path-free handoff surfaces, combined claim competition, canonical structured results, result/event publication, cross-protocol fallback and native loader removal remain pending; normative TR4-06-05/TR4-15-03 and release gates remain open.

## NS15.03 mixed delivery selection - October 1, 2026

Installed verification: **57 distinct passes**, plus **3 architecture checks**. Canonical ready sessions now participate in existing delivery priority/equivalence selection; ambiguous or unresolved ownership refuses before claims/effects. Canonical IDs stay out of legacy harness foreign keys and legacy fallback cannot call the canonical target through old constructors. See [scope](M12_NS15_03_DELIVERY_SELECTION.md) and [manifest](test_runs_20261001_ns15_03_delivery_selection.json). Cross-protocol post-failure fallback, handoff delivery, result/event publication and native loader removal remain pending; normative TR4-06-05/TR4-15-03 and release gates remain open.

## NS15.03 logical message workspace - October 1, 2026

Installed verification: **128 distinct passes**, plus **3 architecture checks**. Public MCP message_create accepts an existing workspace_id without resolving a Server-local path, rejects competing/unknown selectors and preserves logical selection through approval re-execution. A new R4 logical workspace reaches canonical conversation delivery/Core. See [scope](M12_NS15_03_WORKSPACE.md) and [manifest](test_runs_20261001_ns15_03_workspace.json). Mixed endpoint selection parity, managed handoff delivery, result/event publication and native loader removal remain pending; normative TR4-06-05/TR4-15-03 and release gates remain open.

## NS15.03 canonical conversation delivery - October 1, 2026

Installed verification: **200 distinct passes**, plus **3 architecture checks**. Existing message/push claims now join R4 open/turn admission atomically, with sender authority revalidation, serial delivery and authenticated receipt projection. Schema 094 preserves logical identity and historical native foreign keys. See [scope](M12_NS15_03_DELIVERY.md) and [manifest](test_runs_20261001_ns15_03_delivery.json). Path-free message selection, mixed endpoint selection parity, managed handoff delivery, result/event publication and native loader removal remain pending; normative TR4-06-05/TR4-15-03 and release gates remain open.

## NS15.03 approved canonical boot - October 1, 2026

Installed verification: **138 distinct passes**, plus **3 architecture checks**. Operator-approved serve boot now uses R4/Core after embedded composition is ready. Schema 093 persists approval/owner authority for admission, dispatch and initial lease checks; stable replay and existing-session guards prevent duplicate boot opening. See [scope](M12_NS15_03_BOOT.md) and [manifest](test_runs_20261001_ns15_03_boot.json). Delivery, event projection and duplicated native loader removal remain pending; normative TR4-15-03 and release gates remain open.

## NS15.03 implicit canonical selection - October 1, 2026

Installed verification: **85 distinct passes**, plus **3 architecture checks**. REST/MCP opening without endpoint_id selects one matching local canonical realization and refuses canonical/legacy ambiguity before effects. Selection retains subject authority, grants and stable retries. See [scope](M12_NS15_03_SELECTION.md) and [manifest](test_runs_20261001_ns15_03_selection.json). Boot, delivery, event projection and duplicated native loader removal remain pending; normative TR4-15-03 and release gates remain open.

## NS15.03 canonical connection discovery - October 1, 2026

Installed verification: **128 distinct passes**, plus **3 architecture checks**. Existing connection discovery/settings and binding history now project Core catalog and R4 state, with read-only freshness/authority gates and method-disable key revocation. Migrated one obsolete stdio parity test to real MCP HTTP on the same wheel. See [scope](M12_NS15_03_DISCOVERY.md) and [manifest](test_runs_20261001_ns15_03_discovery.json). Implicit selection, boot/delivery, event projection and duplicated native loader removal remain pending; normative TR4-15-03 and release gates remain open.

## NS15.03 limited connection-key opening - October 1, 2026

Installed verification: **95 distinct passes**, plus **3 architecture checks**. Existing limited-bearer opening now uses R4/Core with atomic key linkage, dispatch revalidation and lease expiry/revocation enforcement. Additive schema 092 preserves prior operations/receipts on repeated upgrade. See [scope](M12_NS15_03_KEYS.md) and [manifest](test_runs_20261001_ns15_03_key.json). Implicit selection, boot/delivery, discovery, event parity and duplicated native loader removal remain pending; normative TR4-15-03 and release gates remain open.

## NS15.03 canonical opening - October 1, 2026

Installed verification: **80 distinct passes**, plus **3 architecture checks**. Explicit canonical REST/MCP opening and path-free MCP endpoint connect now use R4/Core, with stable retries, approved-realization validation and endpoint authority. See [scope](M12_NS15_03_OPEN.md) and [manifest](test_runs_20261001_ns15_03_open.json). Implicit selection, boot/delivery, connection-key open, event parity and duplicated native loader removal remain pending; normative TR4-15-03 and release gates remain open.

## NS15.03 canonical session callers - October 1, 2026

Installed verification: **65 distinct passes**, plus **3 architecture checks**. Existing MCP/REST commands and reads for canonical sessions now use R4 admission and Core dispatch, retaining endpoint/grant authorization and stable retries. See [scope](M12_NS15_03_CALLERS.md) and [manifest](test_runs_20261001_ns15_03_callers.json). Opening, boot/delivery, event parity and removal of duplicated native loaders remain pending; normative TR4-15-03 and release gates remain open.

## TR4-15-02 legacy drain and offline restore — October 1, 2026

Final installed verification: **94 distinct passes**, plus **3 architecture checks**. The normative migration-runtime scenario now drains two sessions through the actual TCP Server owner, preserves one uncertain result and restores DB/journal/artifacts into a new home with execution disabled. Fixed actual ENDED casing in adoption and authorized historical reads during disabled execution; mutations and unauthorized reads remain denied. See [scope](M12_NS15_02_DRAIN.md) and [manifest](test_runs_20261001_ns15_02.json). Native runtime deduplication NS15.03, full NS15.04 configuration/post-R4-effect restore and release gates remain open.

## NS15.02 legacy cutover admission fence — October 1, 2026

Canonical binding preparation now consults the migrated endpoint reference, preventing a fresh binding from bypassing legacy active/unknown ownership under a different adapter ID. Two reproductions preceded the fix. Installed verification: **65 passed**, plus **3 architecture checks**. See [scope](M12_MIGRATION_CUTOVER_FENCE.md) and [manifest](test_runs_20261001_migration_cutover.json). Full TR4-15-02 owner drain/rollback acceptance and release gates remain open.

## TR4-15-01 historical migration acceptance — October 1, 2026

The normative installed scenario passed on the unchanged migration-resume wheel: schema 065, historical jobs/claims/messages/events and keys, interrupted batch rollback, public reviewed adoption and repeated offline resume in one database. See [scope](M12_NS15_01_ACCEPTANCE.md) and [manifest](test_runs_20261001_ns15_01.json). TR4-15-01 passes at the migration layer; task dependencies, M4–M6 and all release gates remain open.

## NS15.01 resume after reviewed adoption — October 1, 2026

Installed verification: **62 passed**, plus **3 architecture checks**; eight directed cases overlap the installed suite. The current increment records transactional adoption receipts and validates preserved backup rows when resuming catalog migration. Repeated resume preserves legacy policy and skips generated profiles; changed resources, credentials, missing/incomplete receipts and a live owner refuse migration. See [scope](M12_MIGRATION_RESUME.md) and [verification manifest](test_runs_20261001_migration_resume.json). Full M0–M3 historical-job acceptance, M4 cutover/rollback and release gates remain open.


## NS15.01 reviewed endpoint adoption — October 1, 2026

Nexus 811b597 adds operator-reviewed adopt_endpoint_id to canonical binding preparation. Apply preserves endpoint identity, disabled/denied state and the legacy profile, revalidating source/map/session authority. Installed campaign: **54 passed** across adoption and affected binding/migration regressions. See [scope](M12_MIGRATION_ADOPTION.md) and [manifest](test_runs_20261001_migration_adoption.json). Full phase resumption, normative legacy-history acceptance, cutover and release gates remain open.


## NS15.01 canonical migration denials — October 1, 2026

Nexus 641b538 preserves legacy method denials under canonical adapter IDs during bounded migration batches. Conflicting/changed policy and a live runtime owner refuse migration. Installed verification: **11 migration/backup + 40 admin/architecture = 51 passed**. See [scope](M12_MIGRATION_POLICY.md) and [manifest](test_runs_20261001_migration_policy.json). Reviewed M3 endpoint adoption, normative TR4-15-01 and release gates remain open.


## NS15.01 M2 catalog backfill — October 1, 2026

Nexus d2362e0 adds bounded public migrate-execution catalog batches with verified backup, preserved row digests and atomic migration_map records. Installed campaign: **8 migration/backup + 40 admin/architecture = 48 passed**, including interrupted-batch rollback and repeated resume. See [scope](M12_MIGRATION_CATALOG.md) and [manifest](test_runs_20261001_migration_catalog.json). Operational M3 binding/policy linkage, normative TR4-15-01 and delivery gates remain open.


## NS15.01 M0 database backup — October 1, 2026

Nexus 0f49510 adds the public admin backup command with a consistent WAL-inclusive SQLite snapshot, integrity check and count/digest inventory. Installed verification: **4 backup + 40 admin/architecture = 44 passed**. See [operator procedure and scope](M12_MIGRATION_BACKUP.md) and [manifest](test_runs_20261001_migration_backup.json). Core and Connector are unchanged. Resumable catalog/endpoint backfill, normative TR4-15-01 and all release gates remain open.


## TR4-14-05 Windows process crash — October 1, 2026

Two installed cases passed: abrupt supervisor death before/after process-birth recording, real Job Object tree termination, a separate negative-control process alive, and retained uncertain journal receipt with idempotent replay. See [scope](M11_NS14_05_PROCESS_CRASH.md) and [manifest](test_runs_20261001_ns14_05.json). Product artifacts are unchanged. The normative scenario is qualified for Windows; Linux, additional NS14.05 scenarios and release gates remain open.


## TR4-14-04 combined load — October 1, 2026

Installed verification: **47 passed**, including the normative 100k-identity load scenario and affected authority fixtures. Cache occupancy remains 4,096; measured control emission was 276 ms and the second executor progressed in 104 ms while the first executor was saturated. Product packages remain the capacity-metrics tuple. See [scope and failed preparations](M11_NS14_04_LOAD.md) and [manifest](test_runs_20261001_ns14_04.json). TR4-14-04 passes at the synthetic load layer; task dependencies, provider/platform acceptance and all release gates remain open.


## NS14.04 aggregate operator capacity gauges — October 1, 2026

Nexus 1be8b8e adds pending/dispatch item-byte totals and cache occupancy to the existing local metrics summary for operators, using fixed regular/control categories and no identity labels. Storage failure is reported unavailable; totals retain uncertain reservations. Installed verification: **16 R4 + 37 telemetry/auth/cache/architecture = 53 passed**, including the 100k cache workload. See [scope](M11_CAPACITY_METRICS.md) and [manifest](test_runs_20261001_capacity_metrics.json). NS14.04 remains partial pending combined load and sustained executor fairness; all gates remain open.


## NS14.04 atomic pending admission budgets — October 1, 2026

Nexus 6da5f16 adds 32 productive / 8 control pending-operation limits per executor with separate byte budgets, persisted charges and migration 091. Canonical submission, initial children and native decisions share atomic checks; quota refusals return 429 with Retry-After, and replays retain their original charge. Installed campaign: **62 Nexus R4 + 53 Connector + 4 migration/architecture = 119 passed**, including a last-slot race and parent/child rollback. See [scope](M11_ADMISSION_CAPACITY.md) and [manifest](test_runs_20261001_admission_capacity.json). NS14.04 remains partial; combined load measurement, executor fairness, metrics and all gates remain open.


## NS14.04 dispatch capacity and eligible lanes — October 1, 2026

Nexus c8a07f3 fixes a blocked control backlog hiding eligible work and keeps RECONCILING reservations charged against item/byte limits. Five failing reproductions preceded the fix; six directed cases now pass. Installed acceptance by unique test: **81 Nexus + 53 Connector**, combining the candidate results with a corrected 13-case control follow-up on the same wheel. The raw failures and overlapping runs remain recorded. See [scope](M11_DISPATCH_CAPACITY.md) and [manifest](test_runs_20261001_dispatch_capacity.json). Pending admission quotas, full flood/control load, executor fairness and all release gates remain open.


## NS14.04 bounded authentication cache — October 1, 2026

Nexus a329503 limits positive authentication caching to 4096 entries and TTL to 60 seconds, evicts both indexes together, and prevents a lookup from refilling the cache across invalidation. Installed validation: **100 authentication/HTTP plus 27 R4 cases passed**. Actual SQLite 100k-identity load retained 4096 entries with a memory plateau; hardware, timings, initial failures and fixture corrections are recorded in the [manifest](test_runs_20261001_auth_cache.json) and [scope](M11_AUTH_CACHE_LIMITS.md). Core 0.2.51 and Connector artifacts are unchanged. NS14.04 remains partial; normative flood/control acceptance and all release gates remain open.


## TR4-14-01 crash/restart history — October 1, 2026

The normative restart test passed with two application processes, an abrupt producer exit, natural dispatcher lease expiry and the provider executable removed. Historical intent/operation/session queries and replay work over real HTTP, while ownership remains UNKNOWN, the slot remains reserved and no runtime is constructed. Related installed regression: **33 passed** on the unchanged Core 0.2.51 tuple. See [scope](M11_NS14_01_RESTART.md) and [manifest](test_runs_20261001_ns14_01.json). NS14.01 remains partial; broader dependencies and all release gates remain open.


## TR4-14-02 authority uncertainty and lost revoke ACK — October 1, 2026

Core 18e1727 / 0.2.51.dev0 recovers a committed R4 revoke acknowledgement only after comparing the complete durable fence row, without repeating CAS. Connector 211be74 and Nexus 901fd09 pin the identical wheel. Final installed results: 43 Core, 53 Connector and 36 Nexus cases passed, including four normative NS14.02 variants and NS14.03. See [scope and defect](M11_NS14_02_AUTHORITY.md) and [manifest](test_runs_20261001_ns14_02.json). TR4-14-02 passes at unit_contract; NS14.01 and full task/platform acceptance remain open. No release gate closed.

## TR4-14-03 normative combined recovery — October 1, 2026

The required test_ns14.py::test_ns14_03 now passes on the unchanged final Core 0.2.50 / Connector / Nexus installed tuple. It combines two runtimes, late native open, blocked close and blocked release; proves bounded public response, independent force, retained journals/owner, refused new start and recovery without duplicate opening or force. See [criteria and scope](M11_NS14_03_COMBINED.md) and [manifest](test_runs_20261001_ns14_03.json). The scenario is passed at core_fault_injection on Windows; NS14.03 remains partial because NS14.02 and broader lifecycle/platform acceptance are open. No gate closed.

## Observed stop and durable release — October 1, 2026

Core 29197d2 / 0.2.50.dev0 exposes memory-only shutdown resource facts and fixes stale release markers after stopped-session eviction. Connector 6fc8654 and Nexus 4b63b55 pin the identical wheel. Nexus reports STOPPED/release-pending separately from unknown native state through operator HTTP. Final installed results: 91 Core, 53 Connector, 46 Nexus passed. The failing expiry recovery seed and prior candidate results are retained. See [details](M11_SHUTDOWN_FACTS.md) and [manifest](test_runs_20261001_shutdown_facts.json). Combined late-open/stuck-close/force and platform qualification remain pending; NS14.03 partial, all gates open.

## Retained Server signal shutdown — October 1, 2026

Nexus 23a3ba4 routes signals through the existing retained coordinator instead of stopping HTTP or forcing exit on repetition. Installed verification passed nine R4 and eight legacy cases, including actual serve child processes, Python-delivered SIGINT/SIGTERM, unavailable inventory release, repeated signals, restoration and startup races. See [details](M11_SERVER_SIGNALS.md) and [manifest](test_runs_20261001_server_signal.json). External console/Linux signal qualification and the remaining NS14.03 fault/report/platform matrix stay open; no release gate closed.

## Administrative Server shutdown — October 1, 2026

Nexus f1db502 adds a retained Server coordinator, operator HTTP shutdown/status and CLI commands. One deadline closes productive admission and starts embedded/legacy containment concurrently; legacy release waits for embedded producers and inventory. Installed verification passed 55 R4 plus 26 legacy tests, including a child CLI over real TCP and recovery without reopening. See [details](M11_SERVER_SHUTDOWN.md) and [manifest](test_runs_20261001_server_shutdown.json). SIGINT/SIGTERM, standalone serve-process and full late-open/release/platform acceptance remain pending. NS14.03 partial; all gates open.

## Shared shutdown admission fence — October 1, 2026

Nexus a389087 shares one in-memory fence across R4 and legacy MCP/REST authorization. Lifespan closes it before embedded shutdown waits. Prepared productive R4 requests are refused without operation rows; admitted R4 replay/history, authorized close and trusted external-work return remain available. Installed verification passed 52 R4 and 26 legacy cases on the same wheel. See [details](M11_SHUTDOWN_ADMISSION.md) and [manifest](test_runs_20261001_shutdown_admission.json). The public Server coordinator/command and reachable administrative recovery surface remain pending; NS14.03 partial, all gates open.

## Embedded shutdown deadline and retained recovery — October 1, 2026

Nexus 4a7023b adds a fixed embedded observation deadline, noncanceling pending report, same-owner recovery loop and lifespan retention until resources resolve. A failed composition is removed only after journal cleanup is confirmed. Broad candidate: 106 Nexus plus four legacy cases passed; final wheel after the composition correction: 14 directed plus four legacy cases passed. See [details](M11_EMBEDDED_SHUTDOWN_DEADLINE.md) and [manifest](test_runs_20261001_shutdown_deadline.json). The Server-wide public command, reachable administrative recovery surface, full admission fence and process/release distinction remain pending. NS14.03 partial; all gates open.

## Containment before shutdown storage waits — October 1, 2026

Nexus db3e019 starts retained Core containment before quiesce, outbox stop or historical-reader waits. Journals and ledger remain owned until producers return and Core resources are resolved. Three two-session fault cases failed before the fix and passed after it; 99 installed regression cases passed, including technical Pi child ownership. Core/Connector wheels are unchanged. See [details](M11_SHUTDOWN_STORAGE_ORDER.md) and [manifest](test_runs_20261001_shutdown_order.json). The full public DRAINING_PENDING deadline/recovery contract remains pending; NS14.03 partial and all gates open.

## Bounded parallel identity reads — October 1, 2026

Core c2aed11 / 0.2.49.dev0 preserves full Pi content verification with four bounded readers and ordered results. Connector dca0863 and Nexus 43711b8 adopt the identical wheel. Installed regressions passed: 142 Core, 165 Connector, 89 Nexus. Actual Pi discovery stop passed in 0.0158 seconds; normal handoff/rebind/second-turn journey passed with the unchanged readiness deadline. Source discovery measured 12.51 seconds versus the prior sequential 66.18 seconds, with identical qualified build identity. See [details](M11_PARALLEL_IDENTITY.md) and [manifest](test_runs_20261001_parallel_identity.json). NS14.03 remains partial; all gates open.

## Passive discovery shutdown and lease watcher — October 1, 2026

Core 8d519e0 / 0.2.48.dev0 adds cooperative passive-discovery cancellation and fixes the preexpired lease watcher's pending-event flag. Connector d4cb0c2 and Nexus 79c2d3f stop their inventory readers while retaining started publications. Installed cases passed: 139 Core, 165 Connector, 89 Nexus; two overlapping lease cases additionally verified durable journal events. Actual Pi discovery stop passed in 0.0144 seconds. The normal Pi journey failed the unchanged 120-second readiness deadline and remains unaccepted; shutdown/cleanup succeeded. Profiling measured 55.87 of 66.18 seconds in file opening. See [details](M11_DISCOVERY_SHUTDOWN.md) and [manifest](test_runs_20261001_discovery_stop.json). NS14.03 remains partial; all gates open.


## Approved Codex home and public authentication failures — October 1, 2026

Core 016821f / 0.2.47.dev0 fixes Codex state-directory selection from the approved provider home. Connector 10a123a and Nexus 5d90a85 adopt the same wheel. Installed results: 89 Core, 122 Connector and 21 Nexus cases passed; real public Pi/Codex/Claude missing-login journeys passed; authenticated Codex passed MCP handoff and approved rebinding. A concurrent Pi readiness/shutdown timeout is retained and remains unresolved despite the isolated pass. NS05.05 remains partial; all gates open. See [details](M03_PROVIDER_HOME_ISOLATION.md) and [manifest](test_runs_20261001_provider_home.json).


## Qualified Pi/Codex authentication diagnostics — October 1, 2026

Core 3982f6b / 0.2.46.dev0 adds durable correlated Pi prompt rejection and Codex terminal HTTP 401 classification. Connector 96d11cf and Nexus 581df44 adopt the identical wheel. Installed tests passed: 72 Core (including actual missing-login Pi, Codex and Claude), 122 Connector and 21 Nexus. Retry remains unsafe after a protocol write; operation replay does not send again. Public consumer missing-login journeys and full platform/host acceptance remain pending. See [details](M03_QUALIFIED_NATIVE_AUTH.md) and [manifest](test_runs_20261001_native_auth.json). No gate closed.


## Native terminal failure diagnostics — October 1, 2026

Core 3823ae3 / 0.2.45.dev0 preserves structured Claude/Codex authentication failure codes in durable terminal receipts and concludes Claude result-error operations. Connector e67eb87 and Nexus 12e2c41 adopt the same wheel; Nexus inventory pin and uv.lock are updated. Installed evidence: 58 Core regression cases plus one real Claude missing-login case using the normal qualified factory, 122 Connector cases and 21 Nexus cases. Missing-login evidence for real Codex/Pi and public consumer journeys remains pending; no gate closed. See [details](M03_NATIVE_AUTH_FAILURES.md) and [manifest](test_runs_20261001_native_failures.json).


## Scoped executor recovery guidance — October 1, 2026

Nexus 6184739 adds US English corrective actions for verified executor receipt codes, naming the canonical executor/binding and preserving effect/retry facts. Possible native effects require reconciliation before new work. Installed verification passed 21 Nexus and 60 Connector cases; no Core/Connector product changes or migration. Native missing-login detection is still unproven by this projection test. See [details](M03_EXECUTOR_DIAGNOSTICS.md) and [evidence](test_runs_20261001_executor_diagnostics.json). No release gate closed.


## Reviewed binding lane continuity — October 1, 2026

Connector 2c84b52 adopts a confirmed idle binding replacement without disconnecting other lanes. The exact prior snapshot, complete applied result, unchanged authority, closed/released target observations and post-observation revalidation are required; the ticket deadline is preserved. Installed verification passed 244 Connector tests, four Nexus journeys and two additional continuity/race tests. Real Pi, Codex and Claude each passed initial handoff/close, approved replacement and a second native turn/close on the same installed artifacts. Earlier control-timeout and stale-generation failures remain recorded. This is single-host Windows evidence with test-only Server release readiness; native qualification remains enabled. No release gate is closed. See [details](M03_BINDING_LANE_CONTINUITY.md) and [evidence](test_runs_20261001_binding_lanes.json).


## Explicit reviewed binding replacement - October 1, 2026

Nexus 2a37eda and Connector 4cb5ccf add replace_binding_id / --replace-binding-id, exact reviewed replacement, one binding-revision advance, unchanged endpoint/profile/global agent revisions, scoped target checks and refusal while the target has non-CLOSED claims. Connector schema 12 retains historical applications as SUPERSEDED, uses the current alias and recovers lost acknowledgments without another replacement. The TCP CLI journey exposed an obsolete administrative publication ticket after first apply; the daemon now obtains a current derivative via idempotent registration when canonical authority differs. Final installed verification passed 196 Connector tests and four TCP/HTTP/WSS journeys. The earlier installed campaign passed 34 Nexus cases on the same Nexus wheel and retained the stale-ticket failure; results overlap. [Evidence](test_runs_20261001_binding_replacement.json), [behavior and limits](M03_BINDING_REPLACEMENT.md). Core44 is unchanged. Native opening after rebind, drift/login diagnostics and live unrelated-process continuity remain pending for NS05.05; no milestone or release gate closes.


## Executor-scoped binding aliases - October 1, 2026

Nexus 7398130 fixes the broad endpoint collision guard in prepare and apply. The same agent/workspace may bind the same alias on different executors or different aliases on one executor; same-scope collisions and unscoped legacy endpoints remain refused. The previous installed wheel reproduced both incorrect refusals. Verification passed 24 installed tests, including onboarding, NS05 and the public HTTP/WSS Connector initial-turn/control journey; 19 source cases overlap. Existing endpoint and agent credential fields remain unchanged. Connector 358fd4d and Core44 are unchanged. [Evidence](test_runs_20261001_binding_aliases.json), [scope and limits](M03_BINDING_ALIAS_SCOPE.md). Explicit replacement and live-session revision isolation remain pending; no milestone or release gate closes.


## Durable initial prompt operation - October 1, 2026

Nexus 5d14e58 and Connector 358fd4d accept start text as a separate durable child turn. Opening admission persists the parent relationship; repeated admission preserves IDs. Dispatch waits for READY, an ACTIVE lease and a current SUBMITTED/SUCCEEDED opening receipt, then revalidates source authority and the ordinary send grant before effect. Reuse with text does not open another process. Migration 090 preserves existing rows. Final installed verification passed 77 Connector and 35 Nexus tests, including actual HTTP/WSS public parsed CLI, exact grant consumption, parent outcome changes and upgrade idempotency. Core44 is unchanged. [Evidence](test_runs_20261001_initial_turns.json), [behavior and limits](M04_INITIAL_TURNS.md). Earlier fixture failures and the parent-readiness defect are retained. This implements the initial-child criterion of NS05.04; full M03/M04 acceptance and all release gates remain open. No real-provider or UI acceptance is promoted to these new wheels.


## Canonical session reuse - October 1, 2026

Nexus 2ac9b1c and Connector 8dbd92f implement automatic reuse, explicit existing selection and distinct explicit new sessions under current canonical authority. Confirmation preserves the original opening identity without a second operation, dispatch or native opening. Ambiguity, unresolved claims and authority drift refuse reuse; concurrent automatic admission is serialized. Installed verification passed 76 Connector tests, 82 Nexus tests and one 088-to-089 upgrade/idempotency case. [Evidence](test_runs_20261001_session_reuse.json), [behavior and limits](M04_SESSION_REUSE.md). Core44 is unchanged. The preexisting wrong-agent realization response was corrected from validation 422 to permission-denied 403 after baseline reproduction. Initial prompt as a durable child turn remains pending, so NS05.04 and M03/M04 do not close. Historical real-provider evidence is not promoted to these wheels; all release gates remain open.


## Canonical session observation through Connector CLI - October 1, 2026

Connector ee8294c routes runtime inspect SESSION_ID [--alias ALIAS] and runtime status --alias ALIAS to authenticated Server session reads without starting the legacy daemon. Historical queries tolerate local mapping changes, preserve scope and discard results after credential rotation. The HTTP client validates the closed SessionView shape and negotiated revision; status lists deduplicated sessions referenced by retained intents. Installed verification passed 74 Connector cases and one actual HTTP/WSS public parsed CLI journey, including READY/CLOSED reads after mapping removal and no extra operation or native opening. Nexus test 363686e, product 1ce29ab, Core44 unchanged. [Evidence](test_runs_20261001_session_cli.json). Initial test-query assertion failures are retained. This does not claim complete Server-wide status, process/ownership observations, logs, UI, reuse or retention. Next fixed-plan work is session reuse and its admission/intent correlation; all milestones and release gates remain open.

## Public durable session observation - October 1, 2026

Nexus 1ce29ab adds GET /v1/runtime/sessions/{session_id} with canonical subject/opening-actor/operator authentication, optional executor disambiguation, strict query validation and the normative SessionView shape. It combines durable lifecycle/lease/connection facts without exposing secrets or claiming that a missing handle proves process exit. Expired lease, disconnection and generation mismatch make control unavailable. Installed verification passed 68 tests across session views, receipt history, embedded dispatch and capabilities; pip check passed. [Evidence](test_runs_20261001_session_views.json), [implementation and limits](M10_SESSION_VIEW.md). One collision-fixture constraint failure and the pre-operator campaign are preserved. Core44 and Connector e2012a3 are unchanged. Complete process/ownership observation, CLI/UI consumption, session reuse and retention remain pending under the existing plan. No milestone or release gate closes.

## Same Core44 verified directly and through Connector - October 1, 2026

The installed Nexus 68c6e0b product wheel and Core 9c77871 / 0.2.44 passed the real Pi, Codex and Claude embedded journeys in an environment without the Connector application. All completed governed handoffs, renewed leases, successful turn/close receipts and secret removal, with zero WSS tickets. Codex and Claude each used three explicit operator decisions. MCP used actual loopback HTTP; Pi used application TestClient routes plus its real native socket. [Embedded evidence](test_runs_20261001_core44_embedded.json). Together with the [three Connector journeys](test_runs_20261001_running_launch.json), this campaign passes all six provider/mode cases on the same Core wheel. Connector e2012a3 regression evidence remains 263 installed tests; Nexus regression evidence remains 33. Windows only, Server readiness test-only, no UI/US English or release acceptance. The next fixed-plan work is session reuse, complete runtime observation and retention; remaining M00–M13 and G0–G3 requirements are unchanged.

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
