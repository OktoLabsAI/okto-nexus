# Grouped receipt regression after external attach integration

Base39c5e6cc44481467a6785b09e11219f5c57b2f62. The full Windows suite exposed
an ordinary-inbox regression in test_ack_lands_grouped_receipt_in_sender_inbox.
The external attach integration invoked _deliver_read_receipts once per message,
which split the established grouped sender notification even without external work.

A separate detached worktree reproduced the real behavior:1 FAIL5.64s,
assert2 ==1. No mocks/import failures caused this RED. The frozen source of the
running Windows/Linux suites has not been changed. This is a regression introduced
by the integration milestone, not attributed to the original PR34.

The isolated correction submits the ordinary subset to the existing grouping
routine once, and external messages individually with their operation-specific
acknowledgement evidence. Per-message read events remain unchanged. A new mixed
ordinary/external batch checks two receipt groups, no external evidence on the
ordinary group, one external operation, idempotent repeated ACK, and canonical
completion after explicit external ACK.

Initial correction run:9 PASS1 preparation FAIL12.02s. The new test incorrectly
expected the worker inbox to contain only its two ordinary messages, although
canonical handoff notifications can also be present. The corrected assertion
requires those two IDs to be present and the reserved executable work ID to be
absent. It does not weaken the receipt grouping or consumption assertion.

Expanded isolated Windows receipt/attach/inbox regression completed98 PASS1 POSIX SKIP142.52s (handle54951 exit0). Linux equivalent is RUNNING (handle29305). Sanitized per-node manifests are linked from evidence/p12-receipt-grouping-index.json.
Exact commands, environment, hashes and raw XML are in the private task record
.git/pr34-evidence/receipt-regression-worktree.json. Reduce the terminal XML to
sanitized manifests before integration. Integration into feature/v0.2.0, Linux
qualification, required live MCP smoke and final suites remain pending.

An isolated rerun of the unchanged Claude event-latency test passed1 case3.84s.
This does not erase its full-suite failure or establish its cause. Wait for the
original terminal traceback before changing that test or runtime behavior.
