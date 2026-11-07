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

## PR-05 — internal coordination receipt persistence

Internal coordination receipts now have a Server/actor/workspace/operation/request key, explicit secret-free semantic hash inputs, canonical resource/approval references and a fixed 30-day window. The caller-owned write transaction, approval correlation/deadline, tombstones after message pruning, expiry and bounded retention are tested with real SQLite; eight independent connections and process exits before/after commit preserve one object. Schema 158-to-159 upgrade preserves canonical rows. 73 source tests and 104 installed tests passed, plus an actual isolated installed admin-prune invocation. An existing application sqlite3 import was removed from post-commit binding refresh, with cache-failure recovery/no-regrant tests; the architecture check now scans the imported package. Initial failed reports are retained. The 451-file Python wheel, seven assets and 159 SQL resources match source bytes. Public message/handoff/approval integration, current-authentication and visibility replay gates, canonical outbox/accounting integration, CLI request checkpoint/recovery, expiry refusal, correlated wait and cooperation remain open. These persistence tests do not certify public safe retry.

See [evidence](evidence/pr05-coordination-receipts.md). DX-10 and PR-05 remain in progress. Full R3 and productive M1/M2 remain incomplete.

## PR-05 — canonical coordination creation and recovery

Canonical MCP message_create and handoff_create accept an optional durable client_request_id. Authenticated actor/workspace/operation scope and semantic hash return the original metadata reference, including pending approval, without new inbox/outbox/runtime admission or quota charge. coordination_request_get reads only the authenticated creator reference, with explicit managed capability and workspace authorization; current key/capability and creation permissions are rechecked. Approval execution preserves original authority/provenance and commits the object, receipt, result and granted event in the same canonical transaction. Persisted decision_revision fences stale execution and compensation against a later rejection/reapproval; repository compensation also preserves archive. Real process exits before and after canonical approval execution recover the same request. Schema 158/159-to-160 preserves existing data and receipt deadlines. 74 main source tests, 14 managed-source tests and a separate final four-case race suite passed (overlapping suites); 225 installed behavior tests passed outside the checkout. The final wheel after description compaction passed 53 installed surface/recovery tests with one optional tokenizer measurement skipped. Application/domain bytes are identical to the behavior-qualified wheel. The wheel has 453 Python files, seven static assets and 160 SQL resources matching source bytes. HTTP/MCP/SQLite are real; native execution peers are synthetic. CLI durable checkpoint/recovery/expiry refusal, correlated coordination wait, cooperation smoke and productive local/remote M1 remain open.

See [evidence](evidence/pr05-coordination-creation.md).

## PR-05 — durable terminal coordination and passive observation

Generic participant message/handoff creation, request inspection and correlated wait now use a reusable facade and direct canonical MCP. Durable private checkpoints precede transmission, preserve original actor/workspace/session provenance and both 30-day deadlines, recover the same request after response loss/process death and refuse replay after expiry, backward clocks, missing confirmed receipts or incompatible Server discovery. Passive cursor/snapshot/long-poll rechecks current authority without presence or lease mutation; fresh HTTP authentication also bypasses the positive cache. CLI output preserves confirmed creation IDs if subsequent observation fails; timeout/Ctrl+C never cancel or resubmit work. 614 distinct installed cases passed across overlapping campaigns, with one optional tokenizer measurement skipped. The final 457-Python-file wheel, seven static assets and 160 migrations match source bytes; only the CLI profile-directory guard differs from the broad-qualified wheel. Initial failures and six synthetic fixture-key redactions are recorded. Both initial installed revocation failures were old HTTP-200 expectations; strict HTTP-401 and independent stale-context transaction checks passed afterward. Core/Connector are unchanged. Synthetic native peers do not qualify real productive M1/M2 or two-client cooperation; PR-05 and full R3 remain in progress.

DX-09/10/11 are IMPLEMENTED with separately verified installed subcontracts; the combined qualified-client acceptance remains open. See [evidence](evidence/pr05-coordination-cli.md). The fixed task/scenario/invariant/completion-criterion sets and source hash are unchanged.

## PR-03/PR-04 — optional canonical cooperation smoke

Optional participant cooperation now reviews and separately consents to a directed exchange and then a handoff, using existing canonical MCP requests and durable IDs. Passive reply metadata verifies exact parent/peer/workspace/delivery and receipt or successful native-publication provenance; handoff proof requires exact claim generation and canonical result. Lost responses/process death recover the same IDs; prior consent with a missing request checkpoint permits inspection only and cannot renew a replay window. Historical status/plans and doctor are passive, while current failed revalidation yields UNKNOWN without deleting retained proof. 440 distinct installed cases passed, with one manual A/B campaign skipped. Initial source/installed failures and their fixes are retained. Final wheel has 460 Python files, seven static assets and 160 migrations matching source; only the facade and CLI differ from the broad candidate, with affected cases revalidated. Real HTTP/MCP/SQLite/process behavior is qualified between synthetic identities only; real external-client/provider cooperation, productive M1/M2 and full R3 remain open. Core/Connector are unchanged.

DX-08 is IMPLEMENTED, with installed identity-level subcontracts VERIFIED and qualified external-client cooperation still NOT_RUN. The fixed plan IDs/hash and milestone membership remain unchanged. See [evidence](evidence/pr04-cooperation.md).

## PR-06 — operator attention backend, first increment

Operator attention version 1 now composes the twelve initial kinds, exact filtered snapshots/keyset pages, shared operator seen/snooze CAS and metadata-only SSE invalidation. Additive migration 161 preserves atomic episode anchors across retries, equal timestamps, rollback and canonical history reset. Native actions reuse pure command authority; archival, timezone-equivalent grant expiry and SQLite error paths are corrected. 462 distinct installed cases passed with 0 skipped on Windows outside the checkout. All 470 Python files, 7 static assets and 161 migrations match wheel/source bytes. PR-06 remains IN_PROGRESS: authority-blocking coverage is currently managed-handoff-only; general approvals and remaining message/native policy gates are not claimed. PR-07 client/UI/browser, qualified providers, native service campaigns and full R3 remain open. Connector/Core are unchanged.

Evidence and limits: [pr06-attention.md](evidence/pr06-attention.md).

## PR-06 — approval, result and authority coverage

Attention now includes generic approvals with optional canonical decision CAS; manual/MCP and native handoff results share a stable claim identity and migrated viewing preferences. Pending managed messages, handoffs, queued execution and native decisions revalidate current authority from batched metadata, including relay and notification provenance. Canonical inspection references include message/result/executor IDs, exact handoff selection and maintenance history beyond overview limits; cleanup inspection survives disabled execution without enabling mutations. Migration 162 preserves data/preferences and nullable legacy timestamps; migration 161 is unchanged. 718 distinct installed behavioral cases passed with zero skipped, plus one observation of the known global-feature off/on/off episode-reuse gap. The final 477-Python-file, seven-asset, 162-migration wheel matches source/installed bytes; two changed payloads versus the broad candidate were requalified by 43 installed cases. PR-06 remains IN_PROGRESS for effective global-policy episode generations and client reconciliation; PR-07/browser, real provider/client/service campaigns and full R3 remain open. Core/Connector are unchanged.

Evidence: [pr06-attention-completion.md](evidence/pr06-attention-completion.md). The initial installed nullable-timestamp failure and all corrected/source reports are retained.

## PR-06 — effective Server policy episodes

Effective Server policy now has durable generations for harness integrations and HITL. Only the owning Server lifespan and committed settings activation publish effective values; CLI/env pins, equal-value writes, restarts, rollback and resets preserve their intended semantics. Attention reads policy values and generations in one snapshot and uses them only for responsible denial gates; same-clock recurrence does not inherit seen/snooze, and irrelevant toggles preserve independently revoked-grant episodes. 403 distinct installed cases passed on Windows with zero skipped. The Windows open-SQLite-file unlink test also fails on the previous installed wheel; it remains a recorded limitation and is explicitly deselected in the installed policy group, never counted as passed. Migration 163 is additive, and migrations 161/162 remain unchanged. PR-06 client reconciliation and PR-07 UI/browser acceptance remain open; no real-provider/client/native-service or full R3 acceptance is claimed.

Evidence: [effective policy](evidence/pr06-attention-effective-policy.md).

## PR-07 — integrated operator attention

Attention dashboard and workspace badge now consume the canonical versioned projection. A single client queue batches SSE invalidations, handles opaque cursors/CAS and bounded time refresh, preserves stale authorized snapshots, and clears protected content on forbidden/disabled states. Exact references reuse approval/question, handoff, message, execution and cleanup controls. Canonical revision/claim fences, confirmation, draft preservation on transient reads, explicit invalidation and post-success modal guard reset are implemented. 100 final frontend tests and 10 installed backend contracts passed with zero failures/errors/skips; overlapping reports are not summed. Real Chrome/HTTP/SQLite campaigns exercised preferences, concurrent approval conflict, verification, synthetic native permission/question/denial/120-second expiry, reconnection, feature toggle, stale/403 rendering, keyboard focus and light/dark/narrow/escaped-text presentation. The final 478-Python/163-migration/7-asset wheel matches source and installed bytes. These synthetic-peer campaigns do not qualify real providers, external clients, native user services or full R3.

Evidence: [attention dashboard](evidence/pr07-attention-ui.md). The fixed plan hash and 59 tasks, 132 scenarios, 28 invariants and 17 completion criteria remain unchanged.

## PR-08 — External observation admission

OBS-01..04 are implemented and qualified in Nexus 0.3.3: explicit source consent,
server-owned instance/generation fences, exclusive short-lived publisher tokens,
current authorization before replay, atomic head/event/budget updates, passive
freshness projection, opt-in settings and bounded existing retention maintenance.
Core/Connector are unchanged in this milestone.

525 unique source cases passed, plus 14 installed cases recorded separately and 49
real loopback HTTP assertions. Settings was inspected in Chrome 156, light/dark
and 390 px, including save/reload, invalid TTL refusal and restoration. The package
matches all 486 Python, 164 migration and 7 static payload files byte for byte in
source/wheel/installed form. The disposable Server drained canonically.

See `evidence/pr08-observations.md` and its manifest for original diagnostics,
scope, deduplication and exact artifacts. Injected storage failures are not a
physical-disk-full campaign. Herdr/schema/helper qualification remains PR-09;
external attention and joint regression remain PR-10. Existing real provider,
client and user-service acceptance gates remain open. Full R3 is still in progress.

## 2026-11-06 — PR-09: observador e helper em qualificação

- Implementados `observe herdr bind|run|status`, vínculo explícito, identidade de criação do processo local, transporte só de metadados, journal com exclusão e helper de publicação restrita. A recuperação preserva a incerteza acumulada e nunca troca o reporte pendente por outro conteúdo.
- **316 testes distintos de origem passaram**. Revisão independente cobriu transporte, identidade, persistência, CLI e recuperação; diagnósticos iniciais permanecem no manifesto.
- Herdr Windows x64 **0.9.5/protocolo 22/schema 1**, pacote oficial com checksum e schema instalado retidos. A sessão descartável confirmou working/blocked/idle/done, referência estável de conclusão, renomeação e preservação do done após leitura. O observador fez 53 chamadas permitidas, sem leitura de terminal nem controle.
- O processo observado e os hooks são sintéticos, explicitamente identificados. Isso qualifica a integração com Herdr real, sem alegar execução de provedor/cliente nativo. Wrappers, remote e outras plataformas não são aceitos como identidade comprovada.
- Qualificação com Nexus instalado, casos restantes de troca/desconexão e commit/push PR-09 estão em andamento. Core/Connector não mudaram; PR-10 e os demais aceites integrais R3 continuam abertos.
- [Evidências de progresso](plans/agent_ops/evidence/pr09-herdr-progress.md) e [manifesto inicial](plans/agent_ops/evidence/pr09-herdr/initial-manifest.json).

## 2026-11-06 — PR-09: observador Herdr e helper qualificados

- Entregues `observe herdr bind|run|status`, vínculo explícito com revisão, identidade Windows por processo/criação/imagem/host, transporte só de metadados e helper restrito. Journal persiste intenção/seq antes de cada envio e mantém incerteza até recibo válido; retry histórico explícito não precisa do executável Herdr.
- **318 testes de implementação, dois de regressão CLI e 321 testes instalados passaram**; reruns anteriores não são somados. Wheel final `fe597e0e5a7256d6c3328382d4a046706cba3cc37f4e15e286afad54eab2d29d`: **668 arquivos** conferidos. V2 altera somente o transporte CLI Herdr; os 667 demais arquivos são iguais aos do Server real mantido para a campanha.
- Herdr Windows **0.9.5/protocolo 22/schema 1** real, schema/ZIP/executável com hashes retidos. Processo observado e hooks são sintéticos, explicitamente distintos de OpenAI Codex ou inferência. Campanhas reais cobrem working/blocked/idle/done, referências estáveis, renomeação, dois namespaces com mesmo pane ID, movimentação, substituição e stop/restart.
- A campanha instalada auditou **143 leituras** permitidas; a de estado, 53; a de namespaces, 34. Nenhuma leu terminal ou controlou agente. **147 tabelas canônicas permaneceram idênticas**; conclusão repetida emitiu um único evento observacional; startup/reassociação não inventaram conclusão. TTL expirou para stale/unknown.
- O teste real de move encontrou recusa sem invalidação persistente; V2 corrigiu `HERDR_TARGET_CHANGED` e revalidou o fluxo. Relatórios iniciais permanecem. Quatro strings de credencial sintética em IDs de testes foram redigidas com hashes originais preservados; bearer temporário não foi coletado.
- As duas Herdr foram encerradas canonicamente, com saída dos processos próprios confirmada. Nexus terminou `DRAINED`, sem recursos/erros, e seu PID saiu; a sondagem TCP não conectou. Nenhum serviço pessoal ou provedor foi usado.
- **PR-09 IMPLEMENTED; OBS-05…10 VERIFIED no escopo Windows/local declarado.** PR-10, campanhas reais pendentes de M1/M2/serviços e aceite integral R3 continuam abertos. Core/Connector sem alterações; hash do plano e conjuntos fixos de IDs preservados.
- [Evidências e limites](plans/agent_ops/evidence/pr09-herdr.md), [manifesto de 142 artefatos](plans/agent_ops/evidence/pr09-herdr/artifact-manifest.json) e [uso do observador](docs/herdr-observer.md).


## PR-10a / PR-10b — external observations, canonical precedence and diagnostics

OBS-11 exposes three external watch kinds, exact inspection and complete summaries; its previously published qualification is recorded in [PR-10a](evidence/pr10-external.md). OBS-12 now adds explicit operator-only association, bounded CAS/tombstones, existing-runtime process-birth inspection and canonical-first passive metadata. Canonical receipt/session facts never become an external activity report or execution authority; historical completions remain independent of later association. Additive migration 166 stores only the explicit association and fences. Remote or insufficiently matched observations remain separate.

Nexus 0.3.3 final wheel is `fc9bb8f075ac0167eee9c21d96592b12d46c218df77a0f2114f44b1fc20b1355`. All 681 source/build/wheel/installed files match. V1 passed 736 distinct installed cases; V2 passed 237 affected cases after changing two attention modules. Their union is 756 identities, including 519 unchanged V1 cases not rerun on V2. Frontend passed 130 cases and built with TypeScript/Vite. Actual Chrome/HTTP V1 passed eight synthetic-data checkpoints, preserving 13 canonical tables; all seven static files remain byte-identical in V2. Source, installed and frontend counts are separate. Forty changed Python files pass Ruff.

The first fixed load campaign retained 86 successes and four five-second budget refusals. Reusing the exact current-head predicate avoids loading correlations for working heads that cannot appear in attention. The byte-identical driver measured 90 successes and 0 budget refusals in 90 V2 samples, with no retries or deadline relaxation. Both campaigns retain original reports, failures and canonical-fingerprint/read-only trace checks. This is a measurement of 1/64 sessions and up to 4096 correlated instances, not a general latency SLO.

The same milestone qualifies optional shared diagnostic v1 on Nexus (75 installed cases) and the already published Connector 0.0.12 commit `12d806f955aea84327dd3a33011016d0283ecc18` (93 installed cases). Four fixture files have the same contract digest. Legacy output and exits remain default; typed observation is projected once without new probes or authority. Core 0.0.14 remains unchanged. Test commands and exact installed import guards are retained with the [evidence](evidence/pr10-correlation.md) and [diagnostics report](evidence/pr10-diagnostics-nexus.md).

Compatibility remains additive: absent or invalid associations project null, disabled sources/revoked keys preserve fences, and no association changes canonical execution state. Disable or clear the association through the authorized API to stop projection. Migration 166 is not destructively reversed; retain the database and take a supported backup before any binary rollback. Tombstones consume finite capacity. The five-second proof budget bounds admission, not blocking OS/COMMIT duration; the 32 MiB read budget counts fetched UTF-8 text rather than process RSS.

OBS-12 and OB-19 are VERIFIED in the declared Windows/local contract. PR-10, broader DX-07/DX-14 and full R3 remain IN_PROGRESS. Real OS/Core association, providers, external-client cooperation, native-service lifecycle and productive M1/M2 are not certified by synthetic fixtures. The next implementation dependency is the remote identity/setup path, followed by the still-pending joint and authorized real campaigns. The fixed 59 tasks, 132 scenarios, 28 invariants, 17 criteria and plan hash are preserved.


## PR-03 — remote identity and reviewed setup

Remote identity/workspace bootstrap and the single reviewed project setup are now qualified in Windows loopback with Nexus 187 and Connector 276 installed tests. The six joint cases use real TCP/WSS, a real human operator session, canonical decisions/Finish, durable host state and explicit synthetic native/provider/vault fixtures. Bootstrap is a partial commit with one-shot key delivery, no grant/endpoint or runtime/location activation. Current root/review/credential guards fence prepare, decision and apply. Local amendments retain original bootstrap/history, promote only a matching authenticated handoff and recover a racing prior Finish. Full real-provider/two-host M1/M2, native services, real credential/grant renewal and joint R3 acceptance remain open.

Installed qualification: Nexus 187, Connector 276; 690 and 123 exact package files respectively. Core unchanged. The six TCP/WSS cases preserve canonical authority and Finish, including local review and a racing prior commit. Source/installed counts and overlapping reruns remain separate. Initial failures, recovery limits, package hashes and rollback behavior are retained in [the milestone report](evidence/pr03-remote-bootstrap.md). Usage is documented in docs/remote-project-setup.md. No native service, real provider, personal credentials, registry publication or merge was used.


## PR-03 — remote renewal and explicit credential replacement

Remote grant renewal is qualified with real loopback HTTP/WebSocket, authenticated TCP IPC and DaemonApp: expiry/exhaustion, lost issuance response, same-receipt recovery, unchanged prior leases/sessions, explicit close/new work, canonical key rotation and protected replacement, stale key/ticket/review refusal and historical recovery after revocation. Completed Connector reuse authenticates the current identity and exact approved binding without mutating the old bootstrap or replaying Finish/probe; pending setup remains anchored to its original credential epoch. Submitted issuance stays uncertain during login/vault/recovery failure; a transport failure reading an already confirmed receipt does not reopen issuance uncertainty. Installed tests: Nexus 66, Connector 233. Native/provider behavior remains synthetic; real provider/TLS/two-host, OS-vault lifecycle, native services and complete M1/M2/R3 remain open.

[Qualification, attempts, package pins and limits](evidence/pr03-remote-renewal.md).

## PR-04 dashboard participant guide — 2026-11-07

Dashboard guidance now uses the existing participant CLI for a selected identity/workspace, preserving the public origin and producing no secret-bearing command or extra browser approval gate. The 138 frontend cases and typecheck/build passed. The installed 690-file Nexus wheel served both real loopback browser fixtures; 22 observed checkpoints passed, with 34 unchanged DB comparisons per fixture and canonical shutdown. The initial native-dialog selector error was corrected and retained. No real client/vault/provider/native-service or productive M1/M2/full R3 qualification is claimed. See [evidence](evidence/pr04-participant-guide/milestone.md).

## R3 CI and qualification readiness — 2026-11-07

CI now pins the published Connector renewal wheel a8cf1810 instead of stale 63d99d16. All 123 Connector files match source. A fresh isolated environment resolves declared dependencies with MCP 1.30.0 and passes pip check. The actual installed CI runner passed 8 cases (four remote-renewal and four artifact/pin checks), with unchanged inputs. The finite audit maps 17 completion criteria and 11 RG scenarios without promotion; exact joint, compatibility and public-evidence reviews remain alongside authorized real campaigns. The updated 24-action native-service proposal is prepared only, with no registration/start performed. See [evidence](evidence/r3-qualification-readiness/milestone.md).


## 2026-11-07 — R3: contratos conjuntos instalados

71 casos únicos passaram: 9 de coordenação/entrega mista, 6 de isolamento idle, 17 de modos de sessão e 39 de recuperação selecionada. Dez casos novos e correção mínima da geração da fixture remota; aplicações e wheels inalterados. RG-01/02/03/04/11 verificados no escopo canônico Windows com peers sintéticos. RG-05/06 permanecem em progresso; import audit Core cobre 131 módulos com limites explícitos. Não há promoção de M1/M2 ou aceite global. Evidências e tentativas iniciais: `plans/agent_ops/evidence/r3-joint-contracts/milestone.md` e manifesto adjacente. Compatibilidade, rastreabilidade/revisão pública final e campanhas reais continuam pendentes.


## 2026-11-07 — R3: revisão e redação de artefatos públicos

Revisados 1.822 arquivos públicos dos três repos. Dois valores foram redigidos em relatórios históricos: uma chave UAT e um ticket sintético de fixture. Hashes antes/depois, fonte e falhas originais permanecem documentados; 35 ocorrências restantes são parâmetros inválidos de testes. A segunda varredura confirmou essa classificação. AC-10 permanece aberto: a validade/revogação da chave UAT e commits anteriores não foram alterados ou verificados, e a varredura tem limites declarados. Aplicações/wheels e configurações pessoais inalterados. Evidência: `plans/agent_ops/evidence/r3-public-artifact-review/milestone.md`.


## 2026-11-07 — R3: versões, imports e pacotes

Quatro pares instalados qualificados: versões Core alinhadas aceitas; dois pares cruzados recusados com VERSION_INCOMPATIBLE antes de efeitos. 131 módulos Core importados sob guards, nove controles negativos e stdout bruto retido; fronteiras atuais sem violação. Pacotes completos: Nexus690/Connector123/Core165 arquivos, sem recurso-fonte omitido. RG06/07/08 e AC07 verificados para o snapshot Windows atual. Documentação de compatibilidade e proposta Windows vigente atualizadas. Rastreabilidade vinculada sem somar reruns; RG09, AC09/10 e campanhas reais continuam abertos. Revisão tarefa/cenário a tarefa/cenário segue somente leitura. Evidência: `plans/agent_ops/evidence/r3-compatibility-boundaries/milestone.md`.


## 2026-11-07 — R3: reconciliação literal e lacuna SVC07

Revisados os59 IDs sem novas execuções: BASE/SVC18, DX21, ATN/OBS20. Corrigidos195campos com acentos corrompidos, comprovando apenas reparo de codificação; checker passa a exigir texto literal do plano. ATN/OBS e14contratosDX verificados; seteDX implementados aguardam qualificação real. Contratos puros SVC reconciliados sem transformar adapter injetado em serviço real. AC06/09 e AC10 no escopo dos artefatos entregues verificados; risco histórico UAT/Git continua registrado fora desse aceite, sem novo requisito de reescrita/revogação. Lacuna concreta SVC07 (drain antes de contenção e decisão explícita de força) continua aberta; T06/T12/T13 em qualificação segura. M1/M2/R3 não concluídos. Evidência: `plans/agent_ops/evidence/r3-task-reconciliation/milestone.md`.

## 2026-11-07 — R3: falhas de startup e interrupção da espera

Corrigido o diagnóstico público de porta ocupada: `PORT_IN_USE` no log limitado,
sem texto bruto da exceção nem troca de endpoint/banco. **21 testes instalados
passaram** em snapshot isolado: sete novos e14 reutilizados. Retidos os resultados
anteriores, incluindo6pass/1falha real. T06/T12/T13 verificados: porta realmente
ocupada, falhas reais de configuração/migração/storage e Ctrl+C injetado na espera
do connect com o mesmo processo vivo, depois READY/DRAINED. Nenhum serviço nativo,
provedor ou cofre pessoal utilizado. SVC07 e campanhas reais seguem pendentes.
Evidência: `plans/agent_ops/evidence/r3-service-boundaries/milestone.md`.

## 2026-11-07 — SVC-07: contrato cooperativo do Core

Core publicado em 3cdba87: fence de novas operações, observação passiva e composição de owners do mesmo journal. Foram verificados 217 casos únicos no pacote instalado; tentativas e falhas de preparação permanecem retidas. A mesma wheel 1407014e… foi atualizada nos dois consumidores. Nexus e Connector seguem em validação integrada, sem declarar SVC-07 ou M1 completos. A proposta M1 usará Codex CLI, conta já autenticada e limite total de 200 mil tokens informado pelo usuário; execução real e acesso a credenciais ainda não ocorreram. Evidência: ../okto-nexus-connector-core/docs/evidence/cooperative-drain/milestone.md.

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

## 2026-11-07 — documentação vigente e contratos de recuperação

Corrigidos oito documentos dos três repos: fluxos já entregues deixaram de ser
descritos como futuros; referência Connector confere com75 parsers atuais;
API Core documenta drain cooperativo. Dez helps Nexus passaram e29 recursos
JSON Core conferem com a wheel. Core docs publicado em `f9a5c3b`, Connector em
`55a14a6`; produto e wheels inalterados.

Dois casos físicos existentes passaram nas wheels atuais, em perfis isolados:
Nexus e Connector com start concorrente, reuso, restart e drain, sem serviço
nativo/provedor. Matriz explícita fecha AC-05/08/15 dentro dos contratos;16DX e
SVC-T26/T28 passam a VERIFIED por provas específicas já retidas. Não se somam
nodes de relatórios sobrepostos nem se apresentam mocks como Task Scheduler.
T23/T24 ganham testes focais separados de restart real; sua aceitação ainda não
é antecipada. M1/M2 e campanhas reais permanecem abertos.

Evidência: `plans/agent_ops/evidence/r3-contract-closure/milestone.md`.

## 2026-11-07 — cenários DX restantes

Reconciliação literal dos21 cenários DX restantes:16 contratos verificados,
cinco campanhas reais mantidas pendentes (T34/T38/T39/T40/T43). O caso existente
de inbox alheia passou nos três parâmetros instalados (`count/peek/history`),
com as mesmas wheels, ambiente isolado e inputs inalterados. Os92 pares de
relatório/node da matriz são referências sobrepostas, não novos testes.
T50 verifica honestidade de aceite; não declara M1 concluído. Não houve produto,
credencial pessoal, provedor ou Task Scheduler alterado neste milestone.
Evidência: `plans/agent_ops/evidence/r3-dx-final-contracts/milestone.md`.

## 2026-11-07 — reinício e ownership de processos

Quatro novos casos passaram no código-fonte e nos pacotes instalados atuais.
SVC-T22/T23/T24 e RG-05 foram verificados no escopo literal: reinício pendente
preserva o filho real, claim e slot; queda/retorno do Server preserva vínculos,
limites e grants e não repete trabalho. A prova usa PID canônico, nascimento,
geração e saída do processo real. O filho fecha com exit0 antes da liberação.
As tentativas de preparação e o PASS invalidado por PID do redirector estão
preservados; não contam como cobertura nova. Não houve mudança de produto,
inferência real ou Task Scheduler. M1 e campanhas de plataforma seguem abertos.
Evidência: `plans/agent_ops/evidence/r3-service-restart-contracts/qualification.json`.

## 2026-11-07 — critérios de aceite contratuais

AC-02/12/16/17 verificados pela composição entre frentes, exclusividade de
instâncias, identidade/preset/limites e preservação da configuração. Auditoria
conferiu74 pares relatório/node existentes e82 entradas públicas estáveis;
não são74 testes novos. AC-01/03/11/13/14 continuam abertos com lacunas literais
específicas. A qualificação de reinício03b3e801 complementa AC14; suspensão real
permanece pendente. Dois clientes MCP podem ter qualificação direta sem provedor
se essa capacidade for comprovada; initialize sozinho não basta. Nenhum código
de produto, inferência ou registro nativo mudou neste milestone.
Evidência: `plans/agent_ops/evidence/r3-acceptance-contracts/milestone.md`.

## 2026-11-07 — dois clientes MCP existentes

AC-03 verificado: MCP Inspector0.21.2 programático e FastMCP2.14.7 abriram
sessões úteis, trocaram mensagem/resposta dirigida com correlação canônica e
reconectaram sem duplicar identidades ou sessões. Um caso passou na fonte e
no Server instalado; são duas execuções do mesmo caso. A tentativa inicial
com oráculo de DTO incorreto foi preservada. Não houve provedor, modelo,
credencial pessoal, adaptador nativo novo ou alteração de produto.
O handoff separadamente consentido de DX08 e a campanha M1 continuam abertos.
Evidência: `plans/agent_ops/evidence/r3-two-existing-mcp-clients/qualification.json`.

## 2026-11-07 — smoke de cooperação com dois clientes

DX-08 verificado com Inspector/FastMCP e TerminalCooperation/CooperationFiles
reais: troca dirigida, consentimento separado do handoff, claim/epoch e resultado
canônicos. Consentimento errado/antecipado não cria efeitos. Reconstituir a
fachada recupera os mesmos IDs sem novas chamadas produtivas. Dois casos passaram
na fonte e nos pacotes instalados: um novo e o caso AC03 requalificado porque o
helper compartilhado mudou. Não houve produto, modelo, credencial pessoal ou
serviço nativo alterado. M1 e launcher/cofre de DX04 continuam separados.
Evidência: `plans/agent_ops/evidence/r3-two-mcp-cooperation/qualification.json`.

## 2026-11-07 — contratos de tarefas restantes

DX-15 e DX-16 verificados por suas provas literais de fachada/reuso e descoberta/
revisão. A auditoria conferiu63 registros PASS em12 XMLs e62 hashes; não executou
testes novos. BASE06/SVC07/DX04/DX17/DX18/DX20 mantêm as lacunas mínimas próprias:
primeiro uso e configuração reais, encerramento externo e launcher/credencial.
DX08, ainda pendente na matriz original, foi concluído depois em4455b841 e não
foi rebaixado. Não se exige inferência paga por definição para provar DX04.
M1 e as campanhas de serviço/plataforma continuam pendentes.
Evidência: `plans/agent_ops/evidence/r3-remaining-task-contracts/milestone.md`.

## 2026-11-07 — inicialização nativa isolada de DX-04

O ParticipantLaunch instalado iniciou o Codex 0.167.0 em perfil descartável,
com console próprio e chave Nexus sintética importada por stdin para um alvo
exclusivo do cofre Windows. A tela de login foi observada por rótulos fixos;
nenhuma entrada, credencial de provedor ou solicitação produtiva foi enviada.
Não foi observada autenticação MCP nativa. O único initialize HTTP 401 foi o
controle negativo sem bearer do próprio harness.

A tentativa 001 falhou antes de CreateProcess: o binding de CreateJobObject
não aceitou nome None. A correção exclusiva do harness passou no diagnóstico
benigno com CLI --help, TTY nos três streams e Job vazio ao terminar. A tentativa
002 iniciou o cliente, mas o watcher registrou PermissionError de causa não
demonstrada. O resultado original continua UNCONFIRMED. O Job foi encerrado à
força com código 125 e zero processos ativos; o listener do Server foi fechado
e o alvo próprio do cofre ficou ausente. O agregado cleanup_confirmed=false
é preservado, assim como a ausência dos pós-checks abortados no runner.

A conferência posterior confirmou os hashes dos inputs da tentativa 002. As
contagens finais canônicas foram lidas em modo somente leitura; não há baseline
retido para afirmar igualdade antes/depois. Esses fatos não substituem os
pós-checks ausentes nem promovem o resultado original.

DX-04 permanece IMPLEMENTED: startup, vault e controle negativo não comprovam
consumo da credencial pelo cliente. Não houve alteração de produto, inferência,
acesso à conta autenticada, registro de serviço nativo ou novo aceite de M1.
As propostas e perguntas pendentes de autorização/orçamento continuam válidas.
Evidência: `plans/agent_ops/evidence/r3-dx04-native-startup/milestone.md`.

## 2026-11-07 — tolerância de orçamento M1

O usuário informou: “pode exceder o limite em 500k tokens”. A interpretação
registrada é 500 mil adicionais aos 200 mil originais, total de 700 mil tokens.
Mantém-se a interrupção preventiva aos 100 mil tokens reportados, no máximo
seis admissões seriais incluindo testes de setup, e recusa de novas admissões
quando a contabilidade estiver incompleta. A margem não é uma meta de consumo.
O fluxo nativo continua sem corte atômico de tokens; a política é operacional.

A proposta v4 substitui a v3 como referência atual; os artefatos anteriores
permanecem imutáveis. A dúvida de orçamento foi resolvida. Preparação do coletor
de uso/recuperação e autorização de execução real/serviços permanecem explícitas.
Nenhuma credencial real, inferência ou tarefa do SO foi usada nesta revisão;
nenhum status de tarefa/cenário/aceite foi promovido.
Evidência: `plans/agent_ops/evidence/r3-m1-budget-update/m1-codex-campaign-proposal-v4.json`.

## 2026-11-07 — contexto concreto da campanha M1

Conferidos os três pacotes instalados: Nexus 691 arquivos, Connector 124 e Core
166, todos idênticos às wheels fixadas. Os dois nomes de tarefas M1 foram
derivados pelos componentes instalados e consultados como ausentes; nenhum
serviço foi registrado. Homes de campanha ainda ausentes; porta 64507 livre no
instante da preparação, sujeita a nova conferência antes de qualquer efeito.

O executável oficial extraído tinha nome codex-x86_64-pc-windows-msvc.exe, que
não é encontrado pela descoberta PATH local de codex.exe. Uma cópia completa
isolada da distribuição recebeu também esse nome esperado, com os mesmos
bytes; a descoberta passiva confirmou o candidato selecionado. Nenhum binário
foi executado nem a instalação pessoal alterada. Os 48 arquivos da cópia
foram conferidos; não se infere qualificação de helpers por mera igualdade.

O candidato de provider home C:/Users/jpamb/.codex deriva do ambiente/default,
sem abrir arquivos pessoais. A proposta v5 fixa oito ações de lifecycle M1
para seus dois recursos, distintos das 24 ações vazias anteriormente propostas.
Mantém 700 mil de tolerância total e preventiva de 100 mil. Coletor/driver e
integração de campanha continuam em preparação; uso nativo da conta e ações
de serviço seguem sem autorização. Nenhum status de aceite foi promovido.
Evidência: `plans/agent_ops/evidence/r3-m1-execution-context/m1-codex-campaign-proposal-v5.json`.

## 2026-11-07 — driver finito de perda de resposta M1

Preparado driver de cliente que descarta uma resposta de admissão e uma de
decisão, somente após a confirmação canônica correspondente. Reservas duráveis
impedem novo POST; reconstrução usa os mesmos checkpoints e IDs. Uma reserva
forwarding/unconfirmed deixada por crash bloqueia novas admissões/decisões,
mantendo inspeção e interrupt/close canônicos disponíveis.

No build final, 11 casos únicos passaram, incluindo integração com Nexus/Core
instalados, ASGI e SQLite reais e executor nativo sintético. A integração exige
um POST de trabalho, um POST de decisão, um turno e uma resposta sintéticos,
os mesmos IDs após perda, resultado e close. Foram conferidos 992 arquivos
antes/depois e ausência de módulos de produto importados do checkout.
Falhas anteriores de guard de teste e prefixo de rota permanecem preservadas;
a correção do crash foi seguida de requalificação dos 11 casos finais.

Isso prepara instrumentação da campanha, sem qualificar M1, Connector real,
login, inferência ou serviço do SO. A cota de seis envios deste wrapper ainda
não inclui setup:test automaticamente; faltam coletor e integração do runner
antes do primeiro teste produtivo. Nenhuma credencial pessoal ou provider foi
usado, nenhum arquivo de produto alterado, nenhum aceite promovido.
Evidência: `plans/agent_ops/evidence/r3-m1-response-loss/preparation/README.md`.

## 2026-11-07 — contabilidade operacional M1

Coletor determinístico preparado e verificado em 40 casos finais: contagem
cumulativa por thread sem duplicação no replay, escopos/epochs/cursors/gaps,
reservas seriais antes de runtime.start, vínculo posterior aos mesmos IDs,
seis reservas globais, recusa em stream aposentado e preventiva de 100 mil.
A rodada anterior de 39 casos e seus inputs foi preservada; não são 79 casos.
As transições são puras; persistência/dispatch pertencem ao controlador.
Não houve HTTP, provider, processo nativo ou acesso a credenciais.

A proposta v6 esclarece o limite operacional aceito: depois de turno terminal,
ao menos uma observação de uso correlacionada e replay atualizado sem gaps,
o valor continua sendo mínimo observado, não contador final/faturado. A
monitoração de threads anteriores continua para atualizações tardias. Ausência
de uso, regressão, gap ou fonte desconhecida impede nova admissão. O schema
nativo não oferece marcador de uso final nem corte atômico, e não se inventa
essa garantia. Mantêm-se 700 mil de tolerância total e preventiva de 100 mil.

O journal privado do setup é uma fonte distinta, sem os campos do scope da
API pública de trabalho. Sua observação e a integração global com reserva,
driver de perda e abort canônico ainda estão em preparação. Este marco não
qualifica M1 nem autoriza conta, inferência ou serviço; nenhum aceite promovido.
Evidência: `plans/agent_ops/evidence/r3-m1-token-accounting/preparation/README.md`.

## 2026-11-07 — controlador finito M1 preparado

Composição final verificada em 14 casos com Nexus/Core instalados e executor
sintético: journal próprio de setup e eventos canônicos de trabalho compartilham
orçamento e seis reservas; perda de resposta recupera os mesmos IDs; preventiva
de 100 mil e prazo de 120 s selecionam controles canônicos do trabalho ou stop
do dono temporário. Lock exclusivo impede dois controladores; reconstrução
exige reanexar as capacidades de parada correspondentes ao home selecionado.

Os journals anteriores, atribuídos e fechados, são preservados; apenas um novo
journal é aceito por reserva serial. O monitor projeta metadados/uso no SQLite,
sem exportar prompts, respostas ou credenciais. Setup encerrado exige namespace
exato e reserva própria liberada, além de close SUBMITTED/SUCCEEDED conforme o
contrato standalone do Core; SUBMITTED isolado não comprova encerramento.

A primeira rodada teve 1 falha/12 passes e intervenção de cleanup para remover
um gap artificial; permanece diagnóstica, sem aceite. Após correções do oráculo
e finalizer, passaram 13 casos e depois os 14 finais, incluindo negativo de slot
ainda ocupado. A qualificação final é 14 casos únicos, não soma de execuções;
994 inputs ficaram iguais, sem sombras de módulos de produto pelo checkout.

A proposta v7 consolida 700 mil tokens de tolerância, preventiva de 100 mil,
até seis admissões seriais e os recursos exatos. O coletor permanece operacional,
sem garantia de contador final ou corte atômico. Esta preparação não comprova
M1, provider, Connector real ou serviço do SO. A execução real ainda aguarda
autorização para conta e ações de serviço; nenhum status de aceite foi promovido.
Evidência: `plans/agent_ops/evidence/r3-m1-controller/m1-codex-campaign-proposal-v7.json`.

## 2026-11-07 — execução finita autorizada

O usuário respondeu “sim pode executar” à proposta v7: até seis admissões
produtivas seriais, incluindo setup, com tolerância total de 700 mil tokens,
interrupção preventiva em 100 mil tokens observados e prazo de 120 segundos
por operação. Autorizou também 32 ações de serviço nas quatro tarefas
temporárias exatas: 24 da campanha vazia e oito da M1.

A execução usa o Codex 0.157.0 isolado e a conta já autenticada, somente pelo
próprio executável nativo. O agente não lê nem copia credenciais, configuração
ou transcritos pessoais. As propostas anteriores permanecem intactas; o novo
registro guarda a autorização e seus hashes. Preflight, monitoramento,
recuperação pelos mesmos IDs e cleanup canônico continuam obrigatórios.
Nenhum resultado ou critério de aceite é promovido pelo simples consentimento.
Evidência: `plans/agent_ops/evidence/r3-campaign-execution-authorization/authorization.json`.

## 2026-11-07 — correção de caminho após primeiro setup real

O primeiro setup real terminou seu turno e salvou o Finish, mas o CLI retornou
PROFILE_DRIFT: comparava literalmente o provider home aprovado com barras `/`
e o mesmo caminho canônico Windows com `\`. A leitura do recibo confirmou o
mesmo Server, binding, instalação e projeto. Houve uma reserva produtiva e
22.775 tokens observados; o monitor registrou fechamento e liberação do slot.

Corrigida somente a comparação dos separadores em caminhos locais absolutos.
Não há leitura do home, resolução de links, alteração de caixa ou remoção de
`..`. A regressão falha no pacote histórico e passa no corrigido: 14 testes na
fonte e 14 no pacote instalado, incluindo retomada somente por GET e recusas de
caminhos distintos, relativos ou ausentes. Os inputs da qualificação ficaram
inalterados. A tentativa inicial de build sem setuptools foi preservada;
o build offline posterior concluiu normalmente.

O novo cliente tem apenas um payload de produto alterado entre 691. O Server
em execução, o Codex e os pacotes Core/Connector permanecem nos hashes originais.
A retomada será explicitamente cliente corrigido/Server original, pelos mesmos
recibos, sem repetir setup ou acrescentar ações de serviço. A correção e o setup
isolado não comprovam o ciclo produtivo completo M1 nem promovem aceite.
Evidência: `plans/agent_ops/evidence/r3-m1-path-normalization/qualification.json`.

## 2026-11-07 — campanha real dos serviços temporários vazios

Executadas as 24 ações únicas aprovadas no Task Scheduler do Windows, 12 por
componente: instalar duas vezes, iniciar e reutilizar, desabilitar, parar,
recusar início desabilitado, habilitar, iniciar, reiniciar, parar e remover.
Prontidão canônica confirmou instância, geração, versão e supervisor; handles
Windows comprovaram reutilização e saída dos processos próprios. As duas
tarefas foram removidas, todos os owners observados encerraram, a porta 52106
foi liberada e os dados temporários preservados. Os 981 arquivos dos três
pacotes permaneceram iguais aos hashes aprovados.

Duas interrupções da instrumentação foram preservadas: comparação de PATH sem
considerar a normalização feita pelo produto e falha transitória de gravação
WinError 5. As retomadas reconciliaram os mesmos recibos/processos e não
repetiram efeitos; são 24 ações totais, não soma de tentativas. A ordenação
exit/birth do restart foi verificada em execução; o valor isolado de exit da
geração anterior não foi retido separadamente, conforme a curadoria.

SVC-T07 passa a VERIFIED para a topologia Windows observada. T14 permanece
parcial: contexto salvo foi conferido, mas não houve variação deliberada de
cwd/PATH entre instalação/início ou amostra independente do contexto do filho.
T17 não incluiu habilitação repetida nem alteração externa; T20 não incluiu
próximo connect; T27 não incluiu foreground após a remoção. Logon, crash,
logout, suspensão, reboot, credenciais e M1 continuam com seus próprios gates.
O mapa inicialmente incorreto de T14 foi corrigido antes do commit, preservando
as ações e a correção auditável. A campanha não encerra AC-13/AC-14.
Evidência: `plans/agent_ops/evidence/r3-native-user-service-execution/campaign/qualification.json`.

## 2026-11-07 — M1 real parcial, interrupção e cleanup pendente

A campanha real consumiu duas admissões: setup concluído e uma solicitação
útil local. O mínimo observado foi 45.843 tokens (22.775 do setup e 23.068 da
thread de trabalho), sem afirmar faturamento final ou corte atômico. O cliente
corrigido recuperou o mesmo perfil por GET, com bytes do perfil inalterados e
sem repetir setup. O Server e o Codex permaneceram nos pacotes originais.

A publicação do arquivo diagnóstico live-accounting falhou com WinError 5
após a persistência crítica do controlador. O runner gravou o fault permanente
CAMPAIGN_RUNNER_EXCEPTION e selecionou interrupt canônico. A mesma operação
útil chegou a CANCELLED/RESOLVED_TERMINAL com uso correlacionado e sem gaps;
não houve report.json, decisão nativa, perda de resposta injetada, continuação
ou execução Connector. O interrupt ficou SUBMITTED/DISPATCHED; seu ACK não é
apresentado como sucesso. Um close canônico separado chegou a SUCCEEDED e a
sessão ficou CLOSED, com o slot próprio liberado. O fault não foi apagado.

A parada normal do Nexus excedeu 45 segundos; mais 120,948 segundos de leitura
mantiveram o mesmo PID 45144, birth e geração. O harness está STOPPED, mas o
drain conserva SESSION_RECONCILIATION_PENDING/CORE_UNKNOWN. O claim do Core
continua pendente; isso não transforma seu recibo de abertura SUBMITTED em
um recibo terminal UNKNOWN. A admissão do serviço está fechada. A tarefa M1
continua registrada; não houve force, kill, uninstall ou limpeza de journals.
A proposta de uma única parada forçada, vinculada à geração, está pronta e
revisada. A autorização adicional foi solicitada porque a v7 excluía force;
nenhuma resposta foi presumida pelo tempo decorrido.

Preparada correção somente da publicação diagnóstica: WinError 5/32 recebe
retry limitado a 80 ms e pode adiar o snapshot público, preservando poll e
parada por orçamento. Erros do checkpoint privado continuam fail-closed.
Passaram dez testes finais, incluindo um bloqueio real de arquivo Windows
com CreateFileW; a rodada inicial de nove foi preservada separadamente. O
runner corrigido ainda não foi executado com provider. O defeito de drain está
sob investigação separada, sem hotpatch no serviço vivo.

DX-T39 passa de NOT_RUN a IN_PROGRESS, registrando esta tentativa incompleta;
nenhum aceite M1 é promovido. A campanha vazia de 24 ações já encerrada é
independente deste serviço M1 ainda pendente. Não se declara medida completa
de instalação até primeiro resultado útil, pois as wheels já estavam instaladas
e nenhum resultado útil foi entregue.
Evidência: `plans/agent_ops/evidence/r3-m1-partial-execution/campaign/summary.json`.

## 2026-11-07 — Core preserva prova local de liberação no drain

Confirmado e corrigido o defeito observado no cleanup da M1: depois de close,
liberação de slot e eviction, o drain tratava o claim histórico como órfão sem
considerar a prova local de liberação. O Core agora conserva prova limitada ao
opening, epoch e geração exatos; a composição de runtimes do mesmo journal
exige um dono único e revisão estável. Nenhum claim, recibo ou ACK é reescrito.
Época/geração ausente ou ambígua, restart sem prova, capacidade esgotada,
produtores, handles tardios e outras operações pendentes continuam bloqueando.

Passaram 59 casos únicos do Core na fonte e na instalação, incluindo 24 novos.
As falhas iniciais de fixtures/oráculos foram preservadas. O mesmo teste de
integração Nexus falha no pacote histórico e passa no candidato, concluindo
DRAINED sem force/safety e preservando o histórico. A regressão instalada dos
consumidores passou em 18 casos Nexus e 26 Connector; o caso novo já integra
os 18 e não é contado novamente. Inputs ficaram iguais e os 981 payloads dos
três pacotes foram conferidos, com imports exclusivos do ambiente instalado.

Core commit `830f7ce8ef55f018fd4ad6301f97001a6a05bb93`, wheel
`4e677a205f5a486ef7134b8411983420c1c763c3dda274128a9c623ad1b1775d`.
Nexus e Connector receberam bytes idênticos dessa dependência. As versões
permanecem nas branches feature já preparadas; não houve publicação ou merge.
O serviço M1 vivo não recebeu hotpatch nem esse novo Core. Essa qualificação
isolada não transforma a tentativa real cancelada em M1 concluída.
Evidência: `plans/agent_ops/evidence/r3-released-session-drain/qualification.json`.

## 2026-11-07 — contenção M1 autorizada e limpeza concluída

O usuário respondeu “Autorizar essa parada forçada” à proposta concreta da
geração `188be445d44e96d483336ee424008e56`, PID 45144. Após reconferir tarefa,
PID/birth, geração, digest, pacotes históricos e deadline, foi emitido um único
stop --force vinculado à geração. O comando retornou zero e a saída do processo
foi confirmada; somente então foi executado o uninstall já previsto, também
com retorno zero. A tarefa Nexus está ausente, a tarefa Connector M1 nunca foi
instalada e a porta 64507 está livre. Dados e journals foram preservados.

Não houve replay, reset do controlador, hotpatch, término genérico ou inferência
adicional. O total permanece duas admissões e 45.843 tokens mínimos observados;
o fault permanente e o claim histórico pendente continuam retidos. Esta
contenção forçada não comprova parada cooperativa nem transforma o trabalho
cancelado em M1 aceito. A campanha real está encerrada e limpa, porém parcial.

A correção separada do Core foi qualificada e enviada em `830f7ce`; os dois
consumidores receberam o mesmo wheel em Nexus `f44ca088` e Connector `c100002`.
Esses bytes novos não foram aplicados ao processo M1 histórico durante sua vida.
A evolução do plano permanece registrada sem promover os critérios pendentes.
Evidência: `plans/agent_ops/evidence/r3-m1-authorized-containment/closure/summary.json`.

## 2026-11-07 — resumo inicial real e estado das campanhas

DX-T38 passa a VERIFIED no escopo Windows/Codex 0.157.0 observado. A campanha
real partiu de uma home nova e apresentou identidade, workspace, preset
project-generalist, permissões e efeitos na mesma revisão. O teste de conexão
real chegou a SUCCEEDED; Finish salvou o perfil e o binding APPROVED. O cliente
corrigido retomou o mesmo perfil por GET, sem novo setup ou edição do perfil.
Os contratos instalados já retidos de criação atômica, autoridade e rollback
completam a prova de que Finish cria somente os objetos autorizados.

A falha PROFILE_DRIFT e a recuperação com cliente corrigido permanecem no
histórico. Os wheels estavam previamente instalados; isso não mede o intervalo
da instalação até o primeiro trabalho útil de BASE-06. Não houve resultado útil,
decisão nativa, continuação ou campanha Connector nesta tentativa. DX-T39,
DX-T40, DX-T43 e M1 continuam pendentes, assim como os critérios globais.

A página corrente da campanha Windows agora aponta a revisão 4 executada e
suas 24 ações concluídas, em vez da proposta antiga ainda marcada como não
autorizada. Os snapshots históricos não foram alterados. A contenção M1 já
concluída permanece separada da prova de parada cooperativa.

Esta entrega reconcilia evidências existentes. Não executa novo teste, provedor,
serviço ou efeito de autenticação. O limite e o consumo da campanha encerrada
continuam registrados: duas admissões e 45.843 tokens mínimos observados, sem
afirmação de faturamento final. Nenhuma nova autorização é inferida desta revisão.

Evidência: `plans/agent_ops/evidence/r3-m1-onboarding-reconciliation/review.json`.

## 2026-11-07 — observação da configuração reportada pelo Codex

O adaptador descartava campos de política e instruções presentes nas respostas
thread/start e thread/resume. O Core agora conserva oito campos limitados dessa
resposta e emite core/codex_thread_configuration como evento lifecycle da sessão,
antes de consumir a fila nativa. O journal recebe o evento já redigido e vinculado
ao server, executor, sessão e epoch. Não há nova chamada ao Codex, mudança de
política, conteúdo de instruções ou cópia do transcript.

Cada campo é reported, missing ou invalid. Valores ausentes não recebem defaults;
campos de política desconhecidos, valores excessivos e dados que exigem redação
não são apresentados como política completa. A observação inclui modelo,
provider, esforço, cwd, approval policy/reviewer, sandbox e caminhos de instruções.
O limite do payload é 48.000 bytes. Isso observa a resposta; não prova enforcement
do provedor, catálogo completo de ferramentas ou limite atômico de tokens.

Passaram 126 casos únicos do Core na fonte e no pacote instalado, incluindo
40 novos. As três falhas iniciais de fixture e sua correção foram preservadas.
Passaram também 7 casos instalados do Nexus e 26 do Connector, incluindo dois
novos testes de consumo: o evento é preservado em replay/transporte e não cria
resultado, aprovação, pedido nativo ou mensagem. Os 982 arquivos dos três pacotes
e os inputs dos testes permaneceram iguais; não houve imports do checkout.

Core enviado em `7f69d866f19616fcdd1ee83984f3806b1eb85ff5`, wheel `609e0fbbb20855c6b788d2523b0aeb6cdfbf4b3f5c9792c9e4a080284729c9dd`.
Os dois consumidores fixam esses mesmos bytes. Não houve chamada real ao provedor
ou ação de serviço nesta entrega; DX-T43 e M1 continuam pendentes de campanha real.

Evidência: `plans/agent_ops/evidence/r3-codex-thread-configuration/qualification.json`.
