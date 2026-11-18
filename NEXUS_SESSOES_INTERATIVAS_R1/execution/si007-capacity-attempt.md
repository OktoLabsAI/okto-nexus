# SI-007 capacity request and loss recovery

Migration 172 stores the immutable `next_turn` request before a host RPC.
Request identity includes input ID and revision plus the exact Core scope.
The writer checks the FIFO head, original grant, current capability and
lease owner. One unlinked attempt can remain open per exact session. A
repeat recovers the original request. Staging transfers exclusivity to
the canonical turn and retains the original request, held reservation,
R4 operation and hash in the same commit.

Staged consumption uses the existing Core capacity port. The reconciler
asks for the original request and recognizes a committed consumption after
a lost reply. While its outcome is uncertain, the outbox hold stays in
place. An exact expired or released unconsumed reservation can retire the
linked R4 operation only with the local never-sent outbox and no receipt.
The input remains recoverable by its original ID and receipt.

The isolated regression passed 78 cases across interaction, NS-00,
NS-09, the dispatch pump and canonical fairness. Fixture proof includes
reopening the SQLite store, rejecting stale ownership, retaining a staged
operation across rollback, losing the simulated host response and matching
an expired reservation. Runtime qualification, registration with a live
host, and compensation of an outstanding pre-admission request remain
separate work. The global installation uses the earlier candidate and
has had no interaction migrations applied.
