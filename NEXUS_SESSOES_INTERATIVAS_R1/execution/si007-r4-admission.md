# SI-007 canonical R4 admission

One execution writer revalidates the FIFO head, human login, original
grant revision and current capability. It borrows that writer for the
existing R4 resolve and submit steps. The exact input, operation ID, turn
hash, owner generation and held host reservation are paired before
commit. Migration 171 adds that capacity provenance to the existing
input row. The operation, outbox row and input link roll back together.

The shared pump leaves a linked input pending until its original host
reservation is confirmed consumed. The outbox hold is durable and also
keeps an earlier binary from picking an unconsumed operation. The current
pump keeps other turn submits for
that exact session behind a dispatching or uncertain input. Control
operations still have their existing path. The send transaction repeats
the capacity condition. The Core capacity ledger already gates ordinary
and reservation-bound turns before a native write through the same
`acquire_turn_slot` operation. This increment adds no transport messages
or Core contract fields.

The SQLite/HTTP R4 fixture uses an applied lease and synthetic runtime.
It supplies a synthetic held reservation stamped for that exact runtime
scope. It rejects a stale connection generation, checks the staged R4
hash and blocks both the staged and competing turn during the wait.
The rollback check recovers the original queued receipt and the existing
R4 send afterwards. Separate Core capacity regression passed 21 cases.
The combined R4 and session-interaction regression passed 60 cases.
The focused rerun with the durable outbox hold passed 9 cases.

No production path acquires, consumes or recovers capacity for this
queue. This stays closed until the exact claim can complete the host
round trip, revalidate human authority at the shared send gate and handle
uncertain consumption. Acknowledgement continues to require canonical
receipt processing and does not imply settlement. The global install was
not migrated.
