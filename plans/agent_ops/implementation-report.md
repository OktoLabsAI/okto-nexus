# Agent operations R3 — implementation report

Status: preparation and baseline delivered; PR-01, PR-02 and PR-03 in progress.
BASE-06 provider timing and M1–M4 acceptance remain open.

The immutable scope is the repository-root R3 plan. Progress and limitations are
recorded in `ledger.json` and the root ledger. No scenario is qualified merely
because an implementation or fixture exists.

## Preparation

User requested refreshed main branches, version bumps before implementation,
new versioned feature branches, and commit/push at each milestone. All three
branches were created from fetched `origin/main`; tracked worktrees were clean.
Nexus 0.3.3 and Connector 0.0.12 pin Core 0.0.14. No package publication,
protected-branch merge, personal service installation or provider invocation
has been performed.

No schema or protocol changes in this preparation. Historical NXL revisions
remain unchanged. Local candidate wheels are not published releases.

Validation: 34 tests passed on Windows: Nexus import boundaries/HTTP-only CLI/
serve lock (10), Core public documentation (3), Connector boundaries/lock (19),
and isolated wheel install/metadata (2). Commands use `rtk proxy` and the local
Nexus `.venv/Scripts/python.exe -m pytest`; JUnit records are in
`evidence/preparation-{nexus,core,connector,packaging}.xml`. Candidate wheels were
built with `python -m build --wheel`; all 129 Core and 103 Connector Python files
match source bytes. `uv lock --find-links vendor/wheels` and
`uv sync --extra dev --extra serve-lite --find-links vendor/wheels` succeeded.
An initial PowerShell build wrapper returned an error after the successful build
due to an escaped exit variable; the subsequent isolated packaging tests rebuilt
and installed the artifacts successfully. No build failure is concealed.

`scripts/check_agent_ops_ledger.py` confirms complete ID coverage and the plan's
unchanged SHA-256. This is bookkeeping validation only. Core preparation commit
`2093863` was pushed to `origin/feature/v0.0.14`.

Current limitations: baseline map and suites remain incomplete; no new product feature,
native provider campaign, service-manager campaign or browser acceptance is
claimed. Rollback of this preparation is a source-level version revert; there
has been no production data migration or personal configuration change.

## PR-00 — baseline and contracts delivered

`baseline.md` maps current lifecycle, supervision, authorization, native
interaction, setup/Finish, message/inbox/outbox, handoff claims and MCP rendering.
`adr.md` records orthogonal dimensions, canonical truth, observation without
authority, participant/runtime configuration separation and instance/supervisor
ownership. Source evolution from all three original SHAs is recorded.

Corrected the missing inventory Core version constant after the wider suite
exposed it; a runtime/distribution pin test prevents this mismatch. Onboarding
uses its current origin and Bearer-header guidance. Managed MCP-only policy is
distinguished from adding a participant. Historical stdio/CI/auth instructions
were reconciled. Existing frontend tests now have an npm command and CI step.

Validation: 216 baseline tests passed plus production frontend build. See
`evidence/pr00-validation.md` for exact scopes, prior failures, commands and
limits. Empty-home foreground HTTP liveness was 7.811s with canonical `DRAINED`
shutdown; this is not harness readiness. No schema/protocol migration occurred.

BASE-06's real provider first-use timing is pending authorization/environment;
it is not replaced by HTTP timing. PR-00's implementation map is delivered,
while its campaign subacceptance remains open. Next dependency is PR-01.
Rollback: revert the documentation/UI guidance while keeping coordinated
package/inventory pins; no production database downgrade is involved.

## PR-01 first increment — exclusion

Server now holds OS exclusion for both canonical home and DB before bootstrap
or migrations. Diagnostic PID/heartbeat metadata no longer permits stealing a
live process's instance. Real concurrent processes and abrupt-owner-exit tests
exercise the OS primitive; existing foreground shutdown tests remain green.
See `evidence/pr01-locks.md` and XML for exact scopes and remaining lifecycle
work. No new schema, NXL contract or authority was introduced.

The packaged HTML was regenerated after defining LF newlines at its source;
this resolves the earlier build artifact's whitespace check failure. Provider,
service-manager and cross-platform qualification remain pending.

## PR-01 second increment — readiness

Local operator inspection and passive CLI status now correlate OS ownership,
instance identity, generation, PID and active/installed versions. The projection
separates query readiness, storage initialization and admission from provider or
work readiness. It cannot reopen a draining service. No new remote authority or
schema migration was introduced.

The focused 36-test suite passed and a disposable real foreground process
confirmed CLI/HTTP generation equality, canonical DRAINED shutdown and subsequent
stopped status. See `evidence/pr01-readiness.md` for commands and limits. Full
SVC-01/02/04 acceptance remains open; next is local start/reuse orchestration.

## PR-01 third increment — detached local lifecycle

An application facade now coordinates local inspect/start/ensure-running/stop/
restart. Resolved execution context and a durable launch receipt serialize
competing CLIs before the child acquires Server guards and enters `serve`.
Timeout does not repeat or kill a launch. Remote selection is not silently
treated as local. Stop is a generation-checked adapter to the canonical shutdown
coordinator; a correlated durable receipt recovers a lost shutdown response.

Actual Windows subprocesses prove that three concurrent CLIs converge on one
PID/generation, launcher exit preserves the Server, reopen reuses it, restart
changes generation, stale stop fails and canonical drain completes. This is
not qualification of an installed OS service, actual terminal closure or logout.
See `evidence/pr01-start-stop.md`. The complete facade and all SVC acceptance
remain open for supervisor, logs, recovery and Connector integration.

## PR-02 first increment — Connector readiness and shutdown evidence

Connector OS lock acquisition now closes every refused descriptor. Passive daemon
status requires held exclusion, process birth and authenticated IPC agreement on
canonical state/effective-user identity, generation and version. Local readiness
does not infer an authenticated remote link or work authorization. An unavailable
IPC owner is not respawned as absent. The foreground module now honors its
explicit state directory, while stop verifies a generation-correlated receipt.

The affected regression exposed repeated cancellation during attachment HTTP
cleanup. The transport now joins that cleanup without cancelling it again.
46 focused tests and 75 daemon/runtime tests passed. Isolated package validation
and installed lifecycle evidence are in `evidence/pr02-connector-readiness.md`.
The updated candidate wheel was compared byte-for-byte with all 104 source
Python files and its Nexus CI manifest updated. SVC-11 remains in progress.

## PR-02 second increment — shared user-service definition

Core supplies a pure Windows logon-task definition and native-export fingerprint
for the two hosts. The scope excludes OS I/O, Server policy and credentials.
13 tests passed, including native XML validation without registration. Candidate
Core wheels are identical in both consumers and all 130 Python source payloads
match. See `evidence/pr02-core-service-definition.md`. Registration/CAS, installed
supervisor controls and actual user-service campaigns remain open.

## PR-02 third increment — Nexus Windows host integration

The Server now installs/removes its own user logon task through the application
facade, validates ownership/revision/context before native mutations, routes
installed start through Task Scheduler and fences foreground/detached competition.
A database ownership receipt also excludes a different home targeting the same
DB. Stop persists recovery suppression before canonical drain; uninstall retains
all application data. Pending OS effects are retained for bounded observation
or explicit reconciliation instead of blind adoption/overwrite.

159 tests passed with 2 POSIX-only skips; after the final Windows atomic-receipt
fix, 56 affected tests passed, including concurrent real local processes while a
wheel was built. The regression also corrected metadata/startup observation races
and premature ASGI lifetime-lock release. All 411 wheel Python files match the
final source. See `evidence/pr02-nexus-user-service.md` for exact scope, failures,
commands and evidence. Native task syntax was validated without registration;
actual service/login/credential campaigns remain open, as do Connector supervisor
integration, logs and the remaining fixed R3 requirements.

## PR-02 fourth increment — Connector Windows host and launch handoff

Connector now serializes detached launches before the child exists and owns its
instance lock before constructing state/vault/runtime services. Saved context
retains resolved references; existing proxy values resolve ephemerally at launch.
Windows host operations use the shared Core definition, scoped ownership and
native-export fingerprints, route installed start through Task Scheduler and
persist stop suppression before canonical drain. Uninstall preserves data;
foreign/edited definitions and uncertain effects remain explicit.

72 focused tests, 90 runtime regressions and 2 clean-venv package/lifecycle tests
passed. The final wheel's 109 Python files match source, with Windows-only
pywin32 metadata and the unchanged Core 0.0.14 pin. An initial COM lifetime defect
caused access violations despite pytest's success summary; that run was rejected
and the corrected thread-scoped adapter passed subsequent native validate-only
checks. See `evidence/pr02-connector-user-service.md` and its XML/wheel record.

All three remote mains were fetched again and are already ancestors of the
feature branches. No personal task was installed. Full SVC acceptance remains
open for the remaining controls/reconciliation/upgrade/diagnostics, native
service/login/crash/credential campaigns, productive remote work and POSIX
qualification. There is no schema or NXL migration; rollback preserves existing
data and must respect the selected supervisor's drain/ownership receipts.

## PR-02 fifth increment — passive Nexus lifecycle logs

The application facade and CLI now expose bounded `service logs` snapshots and
follow. The same foreground runtime emits coded startup/readiness/shutdown/exit
records after acquiring ownership, with rotation and retention. Neither writer
nor reader accepts arbitrary provider/exception text or credentials. Reading
logs does not bootstrap or inspect/start a service, and Ctrl+C only ends the
observation. Log availability remains separate from service/work state.

49 tests passed with 2 POSIX skips; 12 final log tests passed, including bounded
I/O failure and corrupt-record handling. A new clean venv installed the final
wheel/Core with serve-lite and passed 13 tests outside the checkout, including
real concurrent start/reuse/restart/drain and generation-correlated logs. All
412 Python payloads match source. See `evidence/pr02-nexus-service-logs.md` for
commands, the corrected fault-injection fixture, provenance and limitations.

The new file is diagnostic only; no schema, protocol, runtime authority or work
journal changed. Other passive diagnostics, remaining lifecycle controls and
actual native/user/provider qualification remain open in the fixed R3 ledger.

## PR-02 sixth increment — selected task enablement

Both hosts now expose enable/disable for their owned Windows task, without
starting/stopping active runtime work. Durable intent and Core's pure
enablement-only comparison reconcile a lost response without adopting unrelated
definition edits. Disabled queued workers exit before bootstrap. Disabling can
still work with an unavailable interpreter; enabling validates its context.
The Nexus native adapter also balances COM lifetime on each calling thread.

12 Core, 67 Nexus and 62 Connector source tests passed; 90 coordinated tests
passed in a fresh venv outside checkout with the final wheels. All 412/109/130
Python payloads match source, Core import boundaries pass, the consumer Core
wheels are identical and the CI manifest is coordinated. See
`evidence/pr02-enablement.md` for exact scopes, commands and limits. Native
mutations/login/credential qualification and the remaining fixed-plan work are
still open. No schema/NXL change, personal task registration or release occurred.

## PR-03 first increment — Server-hosted setup recovery

The existing canonical Finish receipt can now be inspected and matched against
the normalized saved setup request. Connector records submission checkpoints
before Test/Finish, recovers committed results without reapplying, and observes
previously submitted tests without replaying a model turn. Its Server-hosted
wizard resumes the saved review before discovery or configuration questions.
Missing test results and older Servers remain explicitly unconfirmed.

Nine focused Nexus tests, 32 Connector tests and 65 coordinated installed tests
passed. The installed suite includes all 24 existing canonical setup tests and
three client/HTTP-handler integration cases with injected lost replies. Package
origins are asserted outside the checkouts, and all 415/114/130 Python wheel
payloads match source byte-for-byte. Connector commit `e365e9a` is pushed;
Nexus coordinates its CI wheel/manifest. Core is unchanged. See
`evidence/pr03-setup-recovery.md` for evidence and limitations.

This increment does not complete M1 or PR-03. The main Nexus connect/preset,
unified identity creation, terminal work and decisions, actual restart and
productive provider campaigns remain open. Tests simulated the provider turn
and cache loss; no real inference, credentials or native task mutation was used.

## PR-03 second increment — initial local Nexus connect facade

Nexus now has a terminal connect entry for an existing authorized agent. It
reuses SVC context/start, records a review and checkpoints under a local profile,
resolves the initial runtime preset to ordinary configuration, and invokes the
canonical HTTP Test/Finish/recovery workflow. Preset provenance stays in the
existing commit receipt. Reconnect reads the current binding without resetting
later settings or granting access again. A unique approved project binding is
reused only after the operator explicitly selects its canonical agent.

Source campaigns passed 18 terminal/transport, 58 service, and 34 setup/process
regression tests. The final installed campaign passed 112 tests with no skips,
including an actual disposable CLI/service/HTTP start-reuse-drain case. All 419
Nexus Python wheel payloads match source bytes; unchanged Connector/Core wheels
are recorded alongside it. See `evidence/pr03-terminal-connect.md`.

The full project preset and M1 are still incomplete: unified identity creation,
coordination permission defaults, login-start review, remote/participant paths,
terminal productive work/questions/decisions/results and native provider
qualification remain required. The synthetic setup tests do not establish real
provider readiness or productive task completion.

## PR-03 third increment — identity in the project review

Local connect proposes a persistent identity/name and explicit generalist
coordination permissions in its existing review. Canonical Finish creates the
identity, workspace, binding, policies and grant in one transaction through the
ordinary agent/key services. Preview/Test do not create an identity. Collision,
rollback and response-loss handling preserve the same identity/key/grant; later
name/role/permission edits survive reconnect. No root key is exported to the
terminal or Finish response. Automatic handoff claiming remains off for the new
preset even when enabled globally; no administrative authority is granted.

Final source validation passed 14 focused tests. Installed validation
covers 159 distinct cases: 158 broad passes plus the corrected presence
assertion passing with `--lf`, with both reports retained and no skipped tests.
Production source/wheel did not change between runs. The 420 Nexus Python payloads match source bytes;
unchanged Connector/Core artifacts are recorded in the same evidence. See
`evidence/pr03-terminal-identity.md`. Real provider/context/coordination and
productive local/remote acceptance remain open, as do full terminal work,
questions/decisions/results, login-start review, remote/participant routes,
operator-session CLI auth, preset evolution and dashboard introduction. M1 and
the full R3 plan are still incomplete.

## PR-03 fourth increment — terminal work and native decisions

Interactive connect hands off to the project work prompt after setup. The new
work facade submits through existing HTTP intents/admission and reads canonical
sessions, events, questions, decisions and results. Local metadata contains IDs,
scope and hashes only. Same-ID recovery preserves uncertain submissions;
request-specific initial-turn correlation avoids presenting an older result
when an opening is reused. Native decisions preserve current actor, recipient,
scope, revision, validity and schema. EOF/Ctrl+C leave pending questions and
service-owned sessions intact, including standalone watch/answer commands.

Source checks passed 29 focused, 44 regression and
2 observer-exit cases. The installed broad campaign passed
99 and failed three cases because the external test copy lacked
the schema fixture. After copying the schema and fixing EOF, the final wheel passed
35 cases including all three failures. These are overlapping campaigns, not
an additive unique-test count. All 423/114/130 Python payloads match sources;
Connector/Core are unchanged. See `evidence/pr03-terminal-work.md` for provenance,
commands, assertions and limitations.

The synthetic native peer verifies the facade and canonical protocol, not actual
provider productivity or context preservation. Default feature_hitl=false
correctly refuses native delivery; its reviewed activation and terminal grant
renewal are still missing. Remote operator/topology, participant, login-start,
preset evolution, dashboard introduction, real native service and productive
local/Connector campaigns remain open. Native-operation recovery does not
complete generic coordination deduplication. R3 and M1 remain incomplete.

## PR-03 fifth increment — native decision activation in the initial review

The same project review can initialize an unset Server-wide HITL/native-decision
policy, explicitly naming its global effect. Test and Finish revalidate its
revision; Finish commits it through SettingsService with the existing setup
receipt. Live cache refresh follows commit and recovers from the current stored
value. Explicit disabled policy, concurrent edits and later revocations survive
reconnect/replay; no participant can initialize the setting or approve itself.

CLI/env values equal to defaults now retain their explicit provenance. Service
contexts carry the original pins through both bootstrap phases. Legacy contexts
keep prior stored-override behavior, while ambiguity cannot authorize onboarding
initialization. Source validation passed 12 focused cases; a broader run passed
82 and exposed one bootstrap-provenance defect, then the corrected process case
passed. The final coordinated installed campaign passed 267 tests with no
skips, including new/legacy process restart and synthetic native delivery. All
423/114/130 Python payloads match sources. See `evidence/pr03-terminal-policy.md`.

This closes the tested local policy-initialization gap, not M1. Terminal grant
renewal, remote operator/Connector routes, participant, login-start review,
preset evolution, dashboard introduction, real native service and productive
provider campaigns remain open. The full R3 scope is unchanged.

## PR-03 — sixth increment: reviewed local authorization renewal

Explicit local work authorize reviews exact expiry, budget and project actions, then uses the canonical grant issuer with an atomic actor/request receipt. Concurrent requests, stale reviews, late rollback and unknown replies preserve one issuance; later revocation and project drift do not cause replay. Existing grants and leases stay unchanged; fresh openings prefer productive remaining authority and old sessions are not silently rebound. 247 installed regression tests passed on the initial candidate; 30 focused tests passed on the final wheel after uncertain-error/display refinements. Remote operator/Connector renewal and real productive local/remote M1 acceptance remain open.

Migration 158 adds receipts, not another grant authority. Connector/Core versions and pins remain unchanged. Local review, issuance, rollback, concurrency, receipt recovery, explicit revocation and existing-session preservation are verified with synthetic native peers. Full M1 acceptance and remaining fixed R3 requirements stay open. See [plans/agent_ops/evidence/pr03-terminal-authorization.md](evidence/pr03-terminal-authorization.md).

## PR-03 — seventh increment: remote human operator client

Human operator login/status/logout reuse existing session authentication and a separate protected-vault namespace. Origin and Server identity are pinned; session-only requests cannot fall back to loopback trust or an agent key. Remote connect reuses an existing approved binding; saved topology is selected before local lifecycle resolution, with no local fallback. Canonical work/receipt recovery, grant renewal and native decisions are verified over human-session HTTP with a synthetic embedded peer. 167 installed regression tests and two focused installed boundary cases passed on the same 427-file Nexus wheel. New remote identity/setup, Connector proposal approval, real OS-vault/TLS accessibility and the two-host productive campaign remain open.

Connector/Core versions and pins are unchanged. The operator cookie stays in the operator-client vault and is never a runtime credential. R3 and M1 remain incomplete. See [evidence](evidence/pr03-remote-operator.md).

## PR-03 — eighth increment: operator decision and Connector continuation

Human operator CLI reviews and decides the original immutable Connector binding proposal through the existing approval API. Review includes actor, Server, subject, workspace, executor, installation, effects, revision and expiry. Participant authority cannot substitute for the operator; expiry, policy drift, rejection and conflicting decisions remain fenced. Lost decision responses recover the canonical receipt without another POST. The real Connector onboarding service and background continuation reopen persisted state and apply the original request once with the participant credential, producing one binding and grant. 30 source Server tests, 17 source Connector tests and 153 coordinated installed tests passed; 24 focused installed cases passed after the Connector README metadata rebuild, with unchanged Python payloads. Synthetic inventory and HTTP adapters establish the contract; real two-host provider work, OS vault/TLS and full M1 remain open.

The CI Connector wheel and digest are updated together; Core is unchanged. DX-T32 is verified at the HTTP/persistence contract boundary, with productive two-host M1 acceptance still pending. See [evidence](evidence/pr03-terminal-binding.md).

## PR-03 — ninth increment: local login startup review

Local connect can include user login startup in the same exact project review. The existing installer and lifecycle perform controlled drain, user-task registration or enablement, and supervised start only after canonical setup is committed. A separate durable host checkpoint recovers partial installation before ordinary startup, preserving the original setup ID, binding, grant and model-test result. Unapproved login choices can be declined; later disable/uninstall is not undone by reconnect. 8 focused source tests and 30 existing connection regressions passed. An initial installed run exposed a concurrent startup metadata wait gap; three focused source checks passed after correction. The final installed campaign passed 169 tests on the 431-file Nexus wheel, including both existing and newly created project identity startup reviews. Native registration/process effects in the new connection tests are injected. Actual login/logout/crash qualification, Connector initial-review integration and complete productive M1 remain open.

The reviewed host effect and its recovery checkpoint reuse existing lifecycle/installation contracts. Connector wizard integration and native qualification remain pending. See [evidence](evidence/pr03-login-start.md).

## PR-03 — tenth increment: Connector login startup review

Connector connect/configure now offer login startup in the same local connection confirmation, with a secret-free instance/context review and an independent durable host checkpoint before native effects. Existing installer/lifecycle contracts perform drain, install or enable, and supervised readiness before remote onboarding continues. Resume preserves the original request and refuses conflicting choices; reconnect preserves later disablement/removal. Operator approval remains the separate authority for remote execution. 74 focused source tests passed before the final JSON-mode guard; 152 Connector and 104 Nexus tests passed against the final installed artifacts. DX-T37 review/decline is verified for the declared Windows contract with injected native effects; actual login/logout/crash/credential qualification and full productive M1 remain open.

See [evidence](evidence/pr03-connector-login-start.md). Fixed R3 and full M1 remain incomplete.

## PR-03 — eleventh increment: remote project policy review

Remote existing-identity onboarding persists project-generalist revision 1 outside portable JSON and includes its native-decision policy effect in the immutable operator review. Approval and Finish revalidate current policy; explicit false values, pins and legacy provenance are preserved. Configuration, origin, grant and optional policy initialization share one transaction; live policy refresh follows the outer commit. Typed uncertain outcomes resume the same apply intent through Connector background recovery without restoring later disablement or revoked grants. 22 Nexus and 37 Connector source tests passed; 127 Nexus and 285 Connector tests passed in fresh installed artifacts. New remote identity bootstrap, real two-host provider qualification and full M1 remain open.

See [evidence](evidence/pr03-remote-preset.md). Full R3 and productive M1 remain incomplete.

## PR-03 — twelfth increment: saved Connector project reconnect

Connector connect resolves a retained canonical project association before credential entry or discovery; bare connect restores its Server, identity and request, while --identity selects an imported identity. The existing vault key is authenticated against current Server/agent/credential revision; approved binding scope and physical root are checked before service effects for completed requests. Reconnect does not reimport a key, reprobe, reapply defaults or renew grants. Revocation, disabled binding, changed mapping and concurrent local edits refuse reuse without fallback. 67 source Connector and 8 source Nexus integration tests passed; the final focused Connector suite passed 37 tests, overlapping those runs. Final installed artifacts passed 180 Connector and 75 Nexus tests. New remote identity bootstrap and full real-provider M1 remain open.

See [evidence](evidence/pr03-connector-reconnect.md). Full R3 and productive M1 remain incomplete.

## PR-03 — thirteenth increment: Connector project review

Connector connect now proposes a sole full host installation without a selection question or executable probe; material ambiguity asks once and Pi keeps its Node/script installation identity. Saved discovery roots and observations are preserved, explicit filters must match inventory, and a changed inventory refuses the review. The existing configure/checkpoint flow supplies current project, label, provider directory and preset defaults; advanced preferences are optional through --customize. Full paths, settings, limits and effects are shown before Finish. Decline performs no registration/probe/daemon effect; canonical operator approval remains separate from participant consent. 90 source tests passed, then 2 full-entry cases passed. The installed packages passed 201 Connector tests plus 2 additional full-entry cases and 22 Nexus integration tests. No production source changed between installed runs. Initial remote identity provisioning, real-provider M1 and the full R3 plan remain incomplete.

See [evidence](evidence/pr03-connector-project-review.md). Full R3 and M1 remain incomplete.

## PR-03 — fourteenth increment: dashboard project introduction and shared identity

Project introduction reads the canonical preset and suppresses automatic onboarding for existing identities, including setup from the terminal. Connections displays stored origin/current configuration; display name and role edits preserve the canonical identity, metadata, history, bindings and grants. 40 frontend, 32 source integration and 76 installed integration tests passed (overlapping suites). Real Chromium interaction against installed FastAPI/SQLite backends verified first/existing use, personalization, focus, themes/mobile and retry; native checks were synthetic. Productive M1, participant setup and preset evolution remain open.

See [evidence](evidence/pr03-project-dashboard.md). Full R3 and productive M1 remain incomplete.

## PR-03 — fifteenth increment: passive project diagnostics

Passive Nexus doctor separates local service, remote reachability, current operator authority, project identity, binding, runtime eligibility, saved session and exact productive result. Remote default reads metadata without vault/network or local fallback; --check-server permits bounded GETs only. Pending identity creation, absent inventory probes, revoked grants and uncertain submissions remain explicit without repair or replay. 52 source tests and 82 installed regressions passed; the final wheel passed 45 focused installed tests and three actual CLI cases outside checkout. These suites overlap. Participant configuration/authentication, MCP, coordination smoke, real-provider/native service qualification and complete R3/M1 remain open.

The final Nexus artifact has 433 Python files and seven static assets, byte-matched to source. Unchanged Connector/Core pins match 117/130 Python files. Default passivity and independent proof levels are scoped verified subchecks; DX-07 and the broad diagnostic scenarios remain in progress. See [evidence](evidence/pr03-project-doctor.md). Full R3 and productive M1 remain incomplete.

## PR-03 — sixteenth increment: optional preset evolution

Optional preset adoption/evolution now uses a canonical readonly diff and the existing authorized Test/Finish transaction. A three-way comparison preserves personalized values; the review includes every affected connection, grant revocation and boot disablement. Concurrent configuration/identity/authority changes and hidden effects are refused. Local active updates disclose their model test; remote existing Connector bindings use human operator authority without host probes or local fallback; disabled runtime stays disabled. Lost responses recover one setup receipt, and old committed requests remain replayable after preset revision advancement. Ordinary reconnect preserves configuration and authority. The current shipped preset remains revision 1; future revisions are injected in tests. The final installed artifact passed 148 tests with eight explicitly disabled browser cases, plus overlapping cleanup (4) and reconnect/old-receipt (3) follow-ups. Five actual installed CLI cases passed. Synthetic native/provider effects and memory vault/HTTP bridges do not qualify real productive M1, OS vault/TLS or two-host execution.

The 436-file Nexus wheel and seven static assets match source bytes; Connector/Core pins remain unchanged. DX-T51 is verified for the declared installed contract. DX-21, PR-03, full R3 and productive M1 remain in progress. See [evidence](evidence/pr03-preset-evolution.md).

## PR-04 — first increment: participant contract and formats

Core now provides a separate pure ParticipantClientConfig with client/build, format/revision, approved origin, selected file scope and an environment credential reference. Claude JSON, Codex TOML and explicit manual export reuse existing owned-entry planning/CAS without weakening managed capability or format qualification. Unrelated configuration and comments are preserved, invalid/duplicate documents and stale plans are refused, and compensation removes only the still-owned entry. 100 source Core tests passed; installed artifacts passed 97 Core, 74 Connector and nine Nexus cases (five Nexus fixture-path errors corrected by copying wheel SQL resources, with both reports retained). Actual Claude Code 2.1.317 and Codex CLI 0.166.0 read generated configs in isolated homes with zero MCP HTTP requests; this proves parsing, not credential resolution, MCP negotiation or participation. The same 131-file Core wheel is vendored in both consumers. Participant init, protected credential/launcher integration, partial-stage recovery and cooperation remain pending.

DX-01 is verified as the pure shared contract. DX-02/03 and PR-04 remain in progress; full R3 and productive M1 are incomplete. See [evidence](evidence/pr04-participant-contract.md).

## PR-04 — participant init and durable local stages

PR-04 participant init and connect now share existing-identity setup: explicit origin/workspace, hidden/stdin/selected-environment key import, Bearer preparation GET, review hash approval, isolated protected vault entry and selected JSON/TOML apply. Separate durable credential/file checkpoints recover the same setup after lost replies; file drift is preserved and runtime/bindings are not changed. Windows backups are restricted before bytes are written and existing replacement ACLs are preserved. Core exposes an optional empty-file protection hook. Source validation passed 105 Core and 22 Nexus cases; final installed validation passed 105 unique Core, 80 Connector and 36 Nexus cases, including an additional uncertain-write recovery case and managed connect regressions. One Core documentation link case initially failed twice because copied fixture references were missing; it passed after copying those files, with all reports retained. Client credential inheritance, participant doctor/MCP negotiation, cleanup/compensation UX, cooperation and full M1/M2 qualification remain pending. No actual user vault, client configuration, service registration or provider inference was used.

DX-03/04/05/06 and PR-04 remain in progress. Full R3 and productive M1 remain incomplete. See [evidence](evidence/pr04-participant-init.md).

## PR-04 — participant doctor

Participant doctor now separates profile/file, credential store/current doctor environment, current identity, MCP negotiation/basic surface, client reload, participation, handoff and work. Passive mode does not read credentials, use HTTP, start processes or write files. Explicit --check-server authenticates the existing key; --check-environment refuses missing references without vault fallback and labels proof doctor_process. Explicit --check-mcp initializes/lists through the existing SDK with pinned origin/mount, bounded time/requests/pages/tools/bytes and private raw diagnostics. Real TCP Nexus negotiation preserves existing agent sessions/runtime/bindings/grants and leaves participation/work unknown. 32 source and 55 installed cases passed; one initial oversized buffered-response failure was fixed and its report retained. The final 444-Python-file Nexus wheel matches source; Core/Connector are unchanged. Actual external harness credential delivery, client-side MCP behavior, OS-vault qualification, cooperation and complete R3/M1/M2 remain pending.

Full R3 remains in progress; see [evidence](evidence/pr04-participant-doctor.md).

## PR-04 — foreground participant launcher

Participant launch reviews the existing authenticated profile, native executable, physical project, file and client home context before a foreground spawn. Only the new child receives the protected credential reference; other participant references are removed without changing the parent environment. Codex requires --no-daemon and a supported actual configuration location; Claude preserves its trust flow and selected file. Durable starting/started/exited receipts fence automatic replay after spawn or checkpoint uncertainty. 19 source and 74 installed tests passed. Initial adapter-name and test-fixture mistakes were corrected; the fixture failure report is retained. Four installed native-client cases exercised Claude Code 2.1.317 and Codex 0.166.0 with present/missing references in isolated homes and protocol modes. Only present credentials produced authenticated MCP initialize against the synthetic responder; absent credentials still yielded zero process exits, so exit is never readiness. No prompts, model turns or tool calls were submitted. The final wheel has 447 Python files and seven static assets matched to source. Real OS-vault/native-client end-to-end use, interactive GUI/TUI qualification, canonical cooperation, compensation and full R3/M1/M2 remain pending.

See [evidence](evidence/pr04-participant-launch.md). Full R3 remains in progress.

## PR-04 — local participant removal and compensation

Participant remove now reviews and compensates only the owned local file entry and isolated setup vault credential, with no Server requests. Retirement precedes effects and separate file/vault checkpoints recover uncertainty without restoring stale backups, rewriting confirmed later edits or reactivating the profile through init/launch. Explicit keep-config preserves changed/manual/unavailable files. Doctor reports retirement without active checks. 24 source cases and one additional native Windows vault case passed; 108 installed regressions passed, followed by four overlapping checks on the final wheel after a removal-error guidance improvement. An initial TOML test expectation was corrected; a real protected-DACL AUTO_INHERITED preservation failure was fixed, with both failed reports retained. Actual Windows Credential Manager tests used only fixture keys in temporary namespaces and confirmed cleanup/absent replay. The final 449-Python-file wheel and seven assets match source; Core/Connector remain unchanged. Canonical cooperation, real-vault/interactive-client end-to-end use, other platforms, native services and productive M1/M2 remain open.

See [evidence](evidence/pr04-participant-removal.md). Full R3 remains in progress.
