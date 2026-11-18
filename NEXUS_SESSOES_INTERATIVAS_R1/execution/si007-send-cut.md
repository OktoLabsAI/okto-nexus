# SI-007 capacity confirmation and send cut

Capacity confirmation compares the exact reservation, immutable request,
operation ID, turn hash and current connection generation. It releases
the existing outbox hold and records the confirmation in one writer
transaction. A repeated confirmation recovers the same result. A
different reservation leaves the entry held.

The shared pump can hold the operator authority fence across the database
send cut. For a linked input, the cut checks the login, approved session
scope, capability revision, original grant revision and capacity proof.
R4 consumes the grant and marks the attempt `SENDING` in the same
transaction that records possible effect on the input. The transport
operates after the writer and authority fence are released.

The integration fixture verifies the waiting state, shared arbitration,
idempotent confirmation, a missing resolver and revoked authority
refusal, possible-effect marking and rejection of a duplicate send cut.
It rolls back that input's attempt and uses the established synthetic R4
path for its original regression. Host consumption and the capability
revision supplied to the linked input are simulated. Runtime activation
requires the capacity acquisition/reconciliation runner, authoritative
capability projection and receipt processing.

The combined R4 and session-interaction regression passed 61 cases. It
included a separate check of the pump's authority fence across the send
transaction and release before transport.
