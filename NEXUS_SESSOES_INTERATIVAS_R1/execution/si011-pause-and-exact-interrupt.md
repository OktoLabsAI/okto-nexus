# SI-011 queue barrier and exact interrupt

Migration 174 stores a pause on the existing stable queue and preserves the
generation that installed it. An explicit control can pause an empty queue.
Resume requires a current scope and active lease. A pause survives an owner
change and leaves the accepted input data, FIFO and receipts intact.

Preparation checks the barrier before picking a head. The R4 pump also
checks it at reservation and again at the send cut. A pause after reservation
leaves the same operation pending until explicit resume. Ordinary controls
retain their existing R4 path.

Migration 175 retains scoped control authority. Admission of an interrupt
with an exact native turn ID commits the barrier alongside the canonical R4
operation. A repeated intent recovers that operation and leaves a later
explicit resume intact. The send cut checks the current human login, the
exact target, capability revision and barrier. The plan's observed-run
target needs a proven adapter mapping. The implementation never substitutes
the most recent turn for an exact target.

The focused executable R4 and queue-control regression passed 14 cases. The
broader session interaction, R4 and migration run passed 117 cases. The
fixture checks the reserved operation, durable pause, exact frame target,
missing and revoked authority and stable interrupt retry. Its host and capability are
synthetic and its interrupt is not executed by a native adapter. Application
registration, UI/CLI controls, live target qualification and the browser
remain pending. The additive schema requires a schema-aware rollback build
that preserves pending operations and the queue barrier.

The offline Nexus 0.3.8 archive passed Twine's strict check. Byte comparisons
matched migrations 169–175 and the exact interrupt module inside the wheel
with their source files. The checked wheel has SHA-256
`a0b33384c3865c83af8afd4a5d88a2d0454001c451abe917d97e7439fc90d66c`.

The earlier 0.3.8 archive seeded two queued inputs in a temporary schema
173 database. The checked archive applied only 174 and 175. Both queue
revisions, input IDs, sequences, texts and delivery states matched their
prior values. The new barriers and provenance were empty by default, the
foreign key check passed, and applying the migrations again did no work.
The earlier archive refused schema 175 without altering that database.
