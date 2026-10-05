# Workspace-aware runtime options — 2026-10-02

`GET /v1/agents/{agent_id}/runtime-options` now combines the selected executor's
published Core facts with current canonical policy. `executor_id` is required;
`workspace_id` is explicit for binding/start eligibility. Unknown, repeated or
empty scope query parameters are refused. Subject/operator scope is authenticated
again within the same transaction as inventory, binding and grant evaluation.

The three flags no longer remain unconditionally false:

- `can_prepare` reflects fresh, connected, compatible inventory, an active
  subject, enabled feature/method and admission availability. Embedded preparation
  requires an operator. Metadata preparation is permitted before technical
  qualification and does not execute the provider.
- `can_bind` requires one pending realization/workspace for the selected
  installation and current revision, plus operator authority. Missing/ambiguous
  selections have explicit reasons. Delegated application after a separate
  operator proof remains supported by binding commands; this projection does not
  yet select such a proposal/proof on behalf of the subject.
- `can_start` requires one current approved binding, actual executable protocol
  readiness, `READY_FOR_RUNTIME` and canonical subject execution authority.
  Authorization is checked without consuming a grant or writing access audit.
  Normal resolve/admission still revalidates every condition.

Core labels, technical states and technical reasons remain unchanged. The Server
verifies the published inventory contract; it does not discover provider paths
or rerun native qualification using its own operating system. Read projections
can materialize existing agent revision counters but create no operation, session,
outbox, grant or native process.

## Verification

34 directed source tests passed. A newly built wheel then passed 35 installed
tests in 84.65 seconds, including scoped binding/inventory reads, NS04 and packaged
OpenAPI. The runner verified all three installed package trees against their
exact wheels and recorded no changed campaign inputs. Dependency check passed.

Nexus wheel SHA-256:
`bcf84f19264fe4233507cca9bb2b5ad0385c7c3dfb59a726afec63d9b67c4af8`.
See [installed campaign](evidence/runtime-options/installed/campaign.json),
[artifact attestations](evidence/runtime-options/installed/installed.json) and
[source results](evidence/runtime-options/source.xml).

The first source run had 15 passes and one test error from a misspelled grant
column (`executions_used` instead of `used_executions`); its report is retained.
The final test confirms that eligibility reads do not consume the grant budget.
Positive READY tests use explicitly synthetic executor assessments and do not
qualify any native provider or independent host.

## Remaining acceptance work

The public intent API still requires the subject's identity; operator inspection
of another agent reports `SUBJECT_IDENTITY_REQUIRED` rather than fabricating
delegation. Public explicit qualification also needs a complete onboarding path:
the existing real Codex/Claude acceptance captures record passive inventory
version `null`, and native qualification happens later during authorized opening.
Those captures do not prove READY eligibility through this new projection.
Do not reinterpret `NOT_PROBED` as READY to bridge that gap.

Follow-up: the Connector now provides explicit byte-bound observation through
`executor probe`; see [implementation and evidence](M03_INSTALLATION_OBSERVATION.md).
The equivalent embedded Server API/UI and full independent-host journey remain
pending. The earlier passive captures above retain their original scope.

Inventory refresh, the full R4 UI journey, delegated eligibility/proposal
selection, independent-host/fault/platform acceptance, final package freeze and
G0–G3 remain open. This change closes the hardcoded-false projection defect;
it does not close the complete onboarding or release requirements.
