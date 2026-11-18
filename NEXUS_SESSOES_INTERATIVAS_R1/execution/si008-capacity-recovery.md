# SI-008 recovery at the capacity boundary

The R4 dispatcher records its exact unsent proof when it refuses a
reserved interactive turn whose Core slot was consumed. Recovery verifies
operation ID and hash, attempt token and owner, terminal outbox state and
absence of a receipt before releasing the original Core reservation.
Release confirmation preserves the operation and its refusal. A lost
reply leaves the same proof available. An operation that crossed the
`SENDING` cut retains possible effect and remains in reconciliation.

An abandoned pre-admission request uses a separate fence. The SQLite
writer checks the original prepared request and input revision. Expired
and cancelled inputs are already fenced. An explicit authorization denial
blocks the original queued input and advances its revision. Core receives
the original attempt and can record release even when it has yet to see a
reservation. The writer retains the terminal host proof. Recovery can
observe an earlier owner on the same executor. A staged request uses its
canonical operation instead.

The focused migrated SQLite suite passed 11 cases in the isolated prefix.
It covers lost release replies, the actual R4 unsent refusal CAS, the
connection-loss path after SENDING, and pre-admission fencing on expiry
and denied authorization. The host replies are fixture data. This
increment adds no migration or public runtime registration. Scheduler
composition and real harness qualification remain pending.
