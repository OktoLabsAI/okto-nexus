# SI-041 recover receipts with admissions disabled

The embedded restart regression now runs with the session interaction flag
enabled and disabled. The disabled cases remove the admission options and
refuse a new queue submission with HTTP 409. Both cases use the real
installed Core/R4 and a synthetic native peer. [Regression and artifact record](si041-disabled-admissions-recovery.json)

A native write with a retained successful outcome recovered as
`ACCEPTED_NATIVE`. A write whose effect remained uncertain recovered as
`DELIVERY_UNKNOWN` with retry disallowed. Both returned their original
input and operation IDs. Unsent work from the retired session remained
`BLOCKED_SESSION` on the original receipt. The restarted dispatch owner
opened no successor and neither input was replayed.

All 29 installed tests passed, including four restart cases and 25 queue
and capacity cases. In the isolated environment, run the regression with
the installed wheels and the tests from the worktree.

```sh
python -m pytest -q tests/execution_r4/test_session_input_runtime.py::test_restart_reconciles_queued_input_receipts_without_resending tests/session_interaction/test_capacity_attempts.py tests/session_interaction/test_queue_storage.py
```

The document package validator passed. Ruff reported
the same two import blocks in the file before and after this increment.
The guide explains how to switch Home in one browser and how to keep
reconciliation active while preparing a Server rollback. [Terminal guide](../../docs/terminal-work.md#roll-back-the-session-interface)

This is a controlled restart of the embedded test owner using the same
disposable test home. The separate browser probe exercises a live Connector and
Pi process while changing Home without restarting them. The full
provider campaign and release decision remain open. Changes are limited
to the regression, guide and evidence. Revert this commit to remove those
changes without touching runtime data. [Live Home rollback](si041-home-rollback-with-queue.md)
