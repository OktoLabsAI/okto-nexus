# Supplemental installed tests after R6 build

R5's 251 installed tests and R6's exact backend equivalence remain separate
historical evidence. A small R6 supplement closes identified Results and
canonical authorization gaps; it does not relabel the 251 as executed on R6.

The supplement uses the already frozen R6 wheel/prefix. Root must issue its
`TESTS_READY.json` after reviewing the single new test file and its exact hash.
Every one of R6's existing 1,824 source/test/build pins must remain identical.
Only that named, previously absent test file may be added. The runner copies
the test/helper closure into a new temporary tree, never application `src`,
and retains all prior origin, installed-payload, helper, process and before/
after source guards. Existing selected tests come from the frozen R6 tree.

The new tests distinguish canonical Nexus handoff rejection from synthetic
migrated historical read states. They are neither model inference nor a
real-harness qualification. New results receive their own phase inventory,
JUnit, source/test hashes, runtime wheel SHA and cleanup evidence.
