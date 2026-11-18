# SI-005 synthetic peer and baseline regressions

The test fixture scripts a single synthetic turn for a full session key and
owner generation. Its two sessions share a short ID but use separate
executors. Acknowledgement can defer or be lost after the input was
accepted. Model end does not settle the turn. A pending question is tied
to the exact turn and blocks its transition until a matching response.

The fixture emits text echo, delta and snapshot events with separate
event and item IDs. A test feeds its output to the actual Core byte-bounded
event buffer. A reader that falls behind observes the overflow and the
synthetic producer still settles. The fixture uses no provider, engine,
network socket, PTY or personal credential.

The final combined source run in the isolated Core 0.0.15 environment
collected these fixtures alongside contract, SQLite and NS-00 tests.
It finished with 30 passes. An earlier run in the checkout's older venv
failed startup for one NS-00 test because that venv still contained Core
0.0.14. The same test passed with the intended installed dependency.

This evidence validates the synthetic driver and the observable boundaries
it supplies. Host ownership, native Pi settled signals, actual
actor revocation, browser rendering and platform shutdown are separate
qualifications.
