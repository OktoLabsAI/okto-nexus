# NS15.03 limited connection-key opening — October 1, 2026

The existing `/api/v1/connections/open` route now opens canonical endpoints
through R4 admission and Core. Key resolution no longer asks the legacy adapter
registry for a canonical endpoint or resolves a server-local path for a remote
binding. Endpoint policy uses the public Core catalog for R4 adapters; native
profile execution remains the executor's responsibility.

Migration 092 adds nullable `execution_operations.connection_key_id`. Admission
revalidates a limited credential in the transaction that inserts the opening and
outbox, then records its key ID. A limited credential cannot admit another action
or replay an opening owned by a different key. The raw bearer is never persisted
in this column or sent to Core.

Dispatch revalidates the opening credential before any productive operation.
An agent-issued key retains its source execution grant; an operator-issued key
still needs a canonical execution grant for native dispatch. Lease issuance and
renewal revalidate the key and source grant, and cannot extend authority beyond
the key's expiry. Revocation does not remove the authenticated subject's interrupt
and close paths. A connection bearer itself remains excluded from general API
and MCP authority.

Directed tests cover both issuing identities, one native opening across retries,
denial of bearer control, a real send-lock barrier followed by key revocation,
expiry or source-grant revocation, refused lease renewal and authorized close.
The migration test copies actual R4 opening/close/receipt rows, reconstructs schema
091 by removing only the new nullable column, applies 092 twice, and compares
all preexisting operation columns and receipts with an intact foreign-key check.
Initial negative-test preparation expected `REJECTED`; the existing outbox uses
`RESOLVED_TERMINAL`. Corrected assertions require that state, permission denial
and zero native opens. No product state was changed to satisfy the assertion.

The installed campaign also reruns canonical admission/dispatch, legacy migration
acceptance, public open/control, local realization and legacy authorization.
All three packages are byte-checked against their wheels. Core and Connector
artifacts are unchanged. Native peers remain synthetic and readiness qualification
is fixture-local; this does not qualify a remote provider or close a release gate.

NS15.03 remains partial. Implicit selection, boot, delivery, connection discovery
and event projection must finish cutover before duplicated native loaders/codecs
are removed. Domain services and historical recovery are retained.
