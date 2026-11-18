# SI-007 FIFO preparation

The SQLite writer selects the first pending input for the exact session
and owner generation. An earlier blocked, paused or uncertain input
prevents a later input from passing it. Preparation expires queued
inputs that have no linked operation and advances the queue revision.
It preserves the stable receipt and leaves a sibling session untouched.
Intake also checks the encoded text against the existing R4 payload
limit so JSON encoding cannot strand an oversized request in the queue.

Fixture tests exercise the encoded payload boundary, expiry at the
deadline, FIFO, stale generation and blocked head. They use migrated
SQLite with synthetic session metadata. The active lease flag in the
fixture is not a live lease or a positive proof of settlement.
The session-interaction and NS-00 regression passed 38 cases together.

Both executor types reserve operations through `reserve_execution_dispatch`
and revalidate at `begin_execution_send`. Handoff deliveries also use
R4 admission and the same outbox. The executor backlog quota counts
storage. It cannot prove an idle session. An ACK can arrive before the
native turn settles. The integration must exclude incompatible work in
both directions, including a remote executor with no in-process set of
active operations. The Core capacity reservation must be tied to the
exact operation/owner and the applied grant before the shared pump sends.

There is still no route, production queue producer or callback from the
pump. This increment changes neither the existing dispatch path nor the
schema. The next increment must admit and link the operation in one
writer transaction and project its outcome without an automatic resend.
