# Binding operator proofs

Status: implemented increment; full R4 delivery remains open.

## Decision

An agent preparing an enabled R4 binding needs operator authority for the
new endpoint/profile. Preparation persists an `execution.binding.authorize`
request in the existing approvals queue, atomically with the binding proposal.
The proposal's `required_approvals` includes the opaque approval ID and the
agent confirmation requirement. No execution resource or runtime grant is
created by preparation.

The existing operator decision route accepts or rejects this request.
`ApprovalService` has a database-only transactional decision registration for
this action. The authenticated middleware context is revalidated in that
transaction. The decision, its result, the scoped proof and the approval event
commit together. Historical message, handoff and native approval actions retain
their existing execution paths.

The proof binds the approval ID, proposal ID/revision, diff hash and current
operator identity guard. The subject remains the proposal's subject. Migration
077 stores the proof on the proposal; the public decision result exposes only
the proposal ID and opaque proof reference. Credentials and their hashes are
not returned as proof material.

The agent applies its proposal using `operator_proof_ref`. Apply compares the
committed decision and proof, current operator guard, subject policy,
configuration/realization revisions, inventory freshness and expiry. Replay of
a committed apply returns the recorded result without producing another
endpoint, profile or grant. A proof is not portable to another proposal and is
not a runtime execution grant. Runtime delegation remains an explicit command.

Reject remains available for expired proposals; approve cannot issue a new
proof for expired or policy-stale proposals. Decision replay returns the same
recorded proof without reissuing it. Operator key rotation invalidates a proof
that has not yet been applied. Existing explicit method denials prevail.

## Consumer contract

The closed HTTP request and response shapes remain unchanged. Connector keeps
the nullable `profile_id`, `diff.requires_operator`, `diff.fields_changed`, and
`required_approvals` in its typed proposal. Its existing apply method transports
the proof reference unchanged. It does not make or apply the operator decision
locally.

New binding approvals are wired in neutral bootstrap without importing the
optional Core until the R4 action is used. Basic Nexus bootstrap remains usable
without the Core extra.

## Remaining work

Reuse under previously approved self-bind policy, UI/CLI orchestration,
initial lease bootstrap, outbox/host composition and final product campaigns
remain required. These administrative proofs do not qualify native approval
or input application, providers, attach, or multi-host execution.
