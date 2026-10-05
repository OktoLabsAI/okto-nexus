# M07 — Recovering receipts after Core commit and before wire projection

Core 0.2.35 exposes prepare_r4_receipt_binding, validate_r4_receipt_binding and project_r4_bound_receipt. The pre-effect record binds the original R4 operation/source to its exact Core semantic hash. Open includes the prepared installation/profile/root and stream semantic in the hash; decisions include the verified native request and response semantic. The record itself contains only bounded source identifiers, action, hashes and a format version. Prompts, operator responses, native request parameters, local paths, environment and credentials are absent.

The Connector persists this association before each of the seven runtime calls. It rechecks the connection after the storage wait. At startup, unresolved bindings are read in bounded pages and their receipts are queried through the public Core journal. An existing fact with the expected namespace, operation, session and Core hash is projected and handed to the durable publisher introduced in the previous increment. This path does not need provider discovery, a runtime handle, an installed lease, or the original sensitive input.

A missing Core receipt remains unresolved. A malformed association or a mismatched Core hash is refused. Neither absence nor a crash creates a NOT_SENT receipt or authorizes reexecution. The association digest detects local corruption; this record is trusted local persistence and is not an authenticated claim accepted from a network peer.

## Persistence and compatibility

The Connector publication database upgrades additively from schema 1 to schema 2 with a nullable projection_binding column. Existing rows keep their metadata and receipts. Legacy reservations without a binding remain pending; no association is inferred after the fact. Old readers reject the newer schema. Full migration/rollback qualification remains M12 work.

The original live projection API keeps its error correlation behavior, including the original receipt operation ID when the submitted envelope is invalid. The shared Core wheel is fixed in both consumers; artifact hashes and installed source-byte verification are recorded in the campaign manifest.

## Verification

The Core tests compare recovered and live projections for all seven actions, verify omission of sensitive content, reject hash/scope/digest mismatches and invalid records, and preserve diagnostics. Connector tests cover failed binding persistence before native open, additive schema migration, a Core commit followed by failed wire persistence, and a binding with no Core admission. Existing publication, cancellation, capacity and authorization tests remain in the installed campaign.

The real Nexus HTTP/WSS technical integration interrupts the close receipt write after the Core's terminal commit. Recovery queries that durable SUCCEEDED fact, publishes it under a fresh ticket and confirms exactly five canonical operations, five receipts and one native open. The old ticket expiry is injected; native behavior and readiness qualification use the existing technical fixture. This is not a process-kill or provider qualification campaign.

## Remaining work

The increment recovers an unresolved publication after its Core receipt exists. It does not complete nonempty session reconciliation, claims/ownership adoption, event replay, Core-to-wire history after publication acknowledgment, ticket rotation, embedded recovery, crash/pressure qualification or the full delivery gates. Those retain their requirements in DELIVERY_PLAN.md. No milestone or release gate is closed.

## Evidence

The installed campaign is recorded in [the manifest](test_runs_20260930_receipt_binding.json), with [final artifact hashes](evidence/receipt-binding-artifacts.json). The shared Core SHA-256 is 20013ae173652ea3726f5b7ae5d7c37e66eac8f9bc319ae3c36f84e70247e760. The initial installed campaign is retained separately; it was superseded by the live-projection diagnostic compatibility fix before any commit or push.
