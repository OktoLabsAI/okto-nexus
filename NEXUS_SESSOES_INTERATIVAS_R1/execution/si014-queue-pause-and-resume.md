# SI-011 and SI-014 explicit queue pause and resume

The exact-session queue offers separate actions to pause and resume pending sends. The dashboard reads an action revision for the current session and queue state. The server rechecks the original operator login, action revision and queue revision when applying the control. Resuming also checks the current active lease, runtime capability and existing execution grant. An unresolved interrupt in that session preserves the barrier, including an interrupt being reconciled after an uncertain outcome.

In Home, Pause queue retains the messages and leaves the current turn running. Resume queue explains when sends can restart and asks for confirmation. The initial confirmation focus is Keep paused. After a committed change, the panel reports the result and restores focus to the queue disclosure. If the result is uncertain, it asks the operator to refresh the queue before another change.

## Evidence

- The focused execution and session interaction run passed 91 Python tests. The authenticated HTTP scenario paused an empty queue, accepted two messages while paused and observed zero native sends even when advancing the dispatcher. After explicit resume it observed dispatch in FIFO order, using the same input IDs and existing grant identity and revision. It also exercised stale revisions, action substitution, changed session generation, foreign origin and logout.
- A SQLite scenario holds the barrier during accepted, dispatched and reconciling interrupt states. After the exact interrupt reaches a terminal state the queue can resume. An interrupt in a separate session does not affect the tested queue.
- The production dashboard build and 410 Node tests passed. Ruff passed on changed Python files.
- Playwright drove headless Microsoft Edge against the built application with a temporary SQLite fixture and synthetic Codex peer. The message stayed queued with zero native sends after closing and reopening the queue and selecting Keep paused via keyboard. Confirming Resume sending produced a resume receipt and one native dispatch of the original input. The UI reported “Message queue resumed” and “Sending to the harness”, with focus on the queue disclosure.

## Delivery and rollback

This increment uses the existing schema and the opt-in session interaction gate. A source rollback preserves any installed durable barrier. Before rolling back the control surface, review paused queues and keep a compatible control path available for an authorized resume. Exact interrupt admission from Home, steer, real harness qualification and human accessibility testing remain open.
