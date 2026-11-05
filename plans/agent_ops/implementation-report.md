# Agent operations R3 — implementation report

Status: preparation and PR-00 in progress. M1–M4 are not accepted.

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
