# Historical authoring helpers

Editing helpers named `prepare_*` or `complete_*` retain the authoring sequence
against specifically allocated temporary worktrees. They are not the current
qualification command sequence and should not be replayed into a live checkout.

The initial R4 freshness helper included an invalid test-only `applyPending`
call; the actual completed tests use `pause(false)`. Current verification is
the retained successful Node/build report and separate browser cut, not that
initial authoring helper. R6 worktree Node/build passes are also intermediate
cuts. Raw worktree/Original EOL differences led to a fresh Original test/build
in `frontend-r6-original`; only those actual compiler bytes entered R6.

Package, installed, browser and performance drivers have their own explicit
READY/input gates and immutable allocations. Later supplementary R6 tests
are recorded in `installed-supplement-r6`, after the original package report
whose `pytest_executed_on_r6=false` describes its earlier scope. The 251 R5
passes are never relabeled as R6 execution.
