# Owned remote outbox dispatch

Status: partial M04/M06 integration; product gates remain open.

## Decision

One `ExecutionDispatchPump` belongs to each authenticated WSS connection after
the Server accepts reconciliation. It reserves bounded durable capacity before
waiting for the shared socket writer. The reader continues handling lease and
control replies. Link credentials and canonical operation authority are checked
again after the writer wait, before the transaction fences the attempt as
`SENDING`. A successful socket write is not a durable executor receipt.

Migration 079 records the reservation connection ID and generation. Reservation,
send, and release compare the exact owner, token, attempt, class, and byte cost.
A replacement connection can release a known fenced owner's `RESERVED` rows;
it cannot release possible sends. Legacy ownerless reservations require separate
reconciliation. No change to the Core wire or shared wheel is necessary.

Shutdown first stops the pump and observes any database producer already in
flight. Canceling a shutdown waiter does not cancel or abandon that producer.
Unsent owned reservations return to `PENDING`. Owned `SENDING` rows become
`RECONCILING`, retaining their attempt and uncertainty until durable evidence
arrives. The original operation remains queryable and is never blindly resent.

Definitive pre-send authority failures resolve the operation with a structured
Server dispatch error and release its capacity. The Server does not manufacture
a Core receipt. Queries without a receipt report possible effect for a fenced
send, and distinguish Server errors from executor receipt facts.

## Evidence boundary

The public integration journey now uses the actual Server pump through WSS for
open, submit, steer, interrupt, and close. HTTP registration, binding approval,
grant, admission, and receipt ingress remain real. Core and the Connector lease
helper are installed in the package campaign; the native peer, readiness gate,
and physical selection mapping are test controlled.

Controlled barriers also cover authority changes while waiting for the writer,
ambiguous send failure, cancellation during a committed database reservation,
and replacement of a fenced reservation owner. Public disconnect/reconnect
keeps the original operation pending reconciliation with no duplicate open.

This does not complete daemon integration, the physical realization resolver,
embedded execution, nonempty reconciliation, WSS receipt ingress, seven-action
governance, or provider qualification. Global shutdown budgets, production
queue limits, watchdog and resource measurements remain required by M11.
The executable and remote readiness flags stay disabled.
