# TR4-15-01: preserved legacy history through M0–M3

`tests/execution_r4/test_ns15.py::test_ns15_01` passes against the installed
Nexus migration-resume wheel. Product code and all three wheels are unchanged.

One schema-065 database contains two disabled/denied endpoints, a denied Pi
method, operator/subject key hashes, a path-derived workspace, legacy profiles
with non-executable command text, a completed task and claimed handoff (epoch 3),
a result message/delivery and an ended harness session with its native event.

The test takes a consistent backup, invokes the public migration CLI to expand
the schema and commit one batch, aborts a subsequent multi-row batch with a SQLite
trigger and verifies rollback. It resumes the bounded batches and repeats the
completed migration twice. The same database then passes through public local
realization and operator-reviewed endpoint adoption. After stopping the owner,
two more CLI resumes preserve the original history rows and hashes byte for byte,
keys, endpoint IDs/denials, workspace association and canonical Pi denial.
The migration map converges to five records, with one approved binding and zero
execution sessions. Foreign-key validation passes. A process constructor sentinel
covers the entire sequence and refuses every spawn attempt.

The first source attempt failed because a function sentinel could not support a
third-party type annotation (`Popen[bytes]`). A subclass sentinel corrects that
test-only preparation; the raw failure is retained. Source and installed runs
cover the same scenario and are not summed. The preceding 62-case installed
regression remains applicable to the unchanged product wheel.

TR4-15-01 is accepted at its specified `migration` layer on Windows/Python 3.13.
NS15.01 dependencies and full M12 closure remain subject to their own evidence.
TR4-15-02 cutover, TR4-15-03 runtime deduplication, TR4-15-04 safe restore and all
release gates remain open. No provider qualification is claimed by this test.
