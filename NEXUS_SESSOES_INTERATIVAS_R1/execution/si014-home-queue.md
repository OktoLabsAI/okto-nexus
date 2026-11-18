# SI-014 message queue in Home

The conversation panel offers a collapsed message queue to the signed-in human. Opening it reads pending inputs for the exact session, in FIFO order. Each entry shows its position and delivery state. Scope and owner generation are verified on each page and receipt. Paging starts again from the first page if the queue revision changed. A paused queue shows that pending inputs will wait for an explicit resume.

An owned, unsent item offers Remove when cancellation is enabled. The request carries the last observed queue and input revisions. If the queue changed or the removal could not be confirmed, the panel requires a fresh read before offering Remove again. A successful receipt confirms removal, refreshes the list and restores focus to the disclosure. Closing the disclosure has no queue control effect.

## Evidence

- The production dashboard build passed, and all 410 Node tests passed.
- Playwright drove headless Microsoft Edge against the built dashboard and real loopback application routes with a temporary SQLite store and synthetic native peer. The first browser run caught a mismatch in the nested scope representation. The final bundle uses the generation carried alongside the queue scope.
- With a synthetic turn in progress, the final browser run queued two messages, opened the list and queued a third message. The attempted removal using the earlier revision received 409. The panel discarded the stale controls and requested a refresh. After the refresh the original entry was removed, focus returned to the disclosure, and two pending entries remained. The final list and its status were also visible at a 360 by 800 viewport.
- The runtime retained one cancelled row and two queued rows. The count of native sends remained one, for the turn already in progress. The temporary test server and browser were stopped. This run used no provider account and did not exercise a screen reader.

## Delivery and rollback

The existing schema is sufficient. Reverting the dashboard bundle removes the queue UI and leaves durable records and scoped API reads available. The existing opt-in setting governs cancellation. SI-014 remains in progress. Pause and resume actions, exact interrupt and steer effects still need their product controls and evidence.
