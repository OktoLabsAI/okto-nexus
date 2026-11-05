# Agent operations R3 — implementation report

Status: preparation and baseline implementation delivered; PR-01 in progress.
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
