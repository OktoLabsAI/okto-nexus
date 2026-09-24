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

Expanded isolated Windows receipt/attach/inbox regression completed98 PASS1 POSIX SKIP142.52s (handle54951 exit0). Linux equivalent completed99 PASS186.89s (handle29305 exit0). Sanitized per-node manifests are linked from evidence/p12-receipt-grouping-index.json.
Exact commands, environment, hashes and raw XML are in the private task record
.git/pr34-evidence/receipt-regression-worktree.json. Reduce the terminal XML to
sanitized manifests before integration. Integration into feature/v0.2.0, Linux
qualification, required live MCP smoke and final suites remain pending.

An isolated rerun of the unchanged Claude event-latency test passed1 case3.84s.
This does not erase its full-suite failure or establish its cause. Wait for the
original terminal traceback before changing that test or runtime behavior.

The original attempt-history upgrade test independently reproduced2 FAIL3.58s because it pinned migrations59..61 while current additive upgrade correctly returned59..64. Only that explicit expected list was updated in the isolated worktree; rollback, snapshot immutability and data-preservation assertions are unchanged. Expanded attempt-history/migration selections completed11 PASS Windows11.07s (25658 exit0) and11 PASS Linux23.10s (82398 exit0).


## Event wait counterexample and stronger mechanism test

An owned fixture process with an explicit0.4s startup delay reproduced a false
polling assertion (observed first-event latency0.583s), without changing runtime
code or native wait behavior. This independently proves that measuring from send
to first event conflates process startup with queue waiting. The original complete
suite traceback is still pending; this is not a claim that its exact delay/cause
has been recovered. The supplemental counterexample records its cleanup honestly:
one process had not yet reported exit at the immediate check, and a subsequent
census after the probe parent exited found no matching child. The first census
included its own Python command and was corrected to exclude it.

The replacement test subscribes both production and deliberate polling consumers
before either owned fixture receives a turn. A gate holds the negative control's
polling clock after actual event publication; the unchanged production iterator
must deliver via its observed real condition notification while that clock remains
held. Releasing the control clock then permits its own delivery. Both ordinary and
0.4s delayed native fixture startup pass (2 PASS1.59s). Bounds are deadlock guards,
not a widened latency SLO. Exact owned Popen handles are waited/reaped in finally,
even when an assertion fails. No installed provider or sandbox override is used.

The whole Claude fixture module completed in the detached worktree:
Windows20768 exit0,29 PASS7 native SKIP60.50s; Linux7925 exit0,29 PASS7 native
SKIP63.34s. The four changed files pass Ruff. Required isolated live
MCP smoke after the receipt production correction passed exit0. Main integration,
full-suite terminal analysis and final-source regression remain required.


## Second pinned migration-list correction

The main Windows full suite subsequently failed the reconciliation upgrade test,
which also expected the migration ledger to stop at61. Isolated unchanged-test
reproduction:1 FAIL3.23s. Explicit expected list now ends at64; repeat application,
prior audit-row preservation, recovery columns, empty reconciliation history and
foreign-key checks remain unchanged. Corrected case:1 PASS Windows2.51s and1 PASS
Linux9.27s (1718 exit0). No runtime or SQL change. The candidate now contains five
changed files, all awaiting main integration after full suites51046/29628 finish.
