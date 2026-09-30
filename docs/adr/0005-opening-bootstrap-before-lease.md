# Opening bootstrap before the first lease

Status: implemented increment; dispatcher owners and full product acceptance remain open.

## Decision

An admitted `runtime.open` with no lease history may be delivered to its
current admitted lane as `OPEN_AUTHORIZED_PENDING_LEASE`. The existing Core
`operation.submit` wire shape is unchanged. It carries the immutable opening
intent, scope, operation ID/hash, current connection, and a canonical grant
selected by the Server's runtime access service.

`begin_execution_send` revalidates the subject, binding, realization,
inventory, profile, connection, lane ticket, and grant in the reservation
transaction. It returns a distinct `AuthorizedOpenBootstrap` with no lease
or Core execution context. Its only permitted use is resolving the approved
local selection and requesting the initial lease. Core still rejects the
operation context until the correlated lease has been installed.

Migration 078 adds the dispatch phase, source grant ID, and connection ID to
the outbox. The bootstrap is fenced as `SENDING` before delivery, with its
exact reservation retained and lease ID/serial left null. A lost response,
failed initial lease, or disconnected channel cannot release it as unsent
or send it again. Recovery must reconcile the original operation and owner.
An existing but unusable lease is not treated as absence of lease history.

## Application boundary

The lease issuer checks the source grant pinned by dispatch. The first lease
cannot move the opening bootstrap to a replacement connection. Current
identity, policy, revisions, profile, ticket, and inventory are still checked
at lease issuance and application.

After the actual Core application ACK, the Server attaches the lease ID and
serial and changes the dispatch phase to `LEASE_AUTHORIZED`, in the same
transaction that marks the lease/session active. The dispatch remains
`SENDING`: the ACK is not a second dispatch or proof that open succeeded.
The Core receipt subsequently projects the session and releases capacity
through the existing ingress path. Later lease renewal preserves the
original receipt provenance; it does not rewrite the dispatched operation.

Other operations require an applied lease and retain grant budget checks.
The administrative binding proof does not supply a runtime grant. None of
these transitions enables the R4 product readiness flags.

## Evidence and remaining integration

The public integration test creates identity prerequisites only. Registration,
inventory/realization publication, delegated operator consent, apply, grant,
tickets, resolution, admission, and receipt publication use HTTP. WSS handles
attach and the initial lease; the real Core opens and submits to a synthetic
native peer. Replay opens once, and Core refuses context before installation.

The dispatcher is explicitly invoked by the test. The approved root mapping
and native peer are test inputs, not the daemon's production realization
resolver. The owning outbox loop, physical selection revalidation, embedded
and daemon composition, nonempty reconciliation, failure receipt recovery,
providers, UI, and distinct hosts remain required.
