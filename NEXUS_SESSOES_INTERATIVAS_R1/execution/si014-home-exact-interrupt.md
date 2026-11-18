# SI-011 and SI-014 exact-turn interruption in Home

The conversation can review and confirm an interrupt against a proven active Codex turn. The review freezes the canonical target and queue revision. The confirmation explains the queue pause and initially focuses Keep turn running. The technical view keeps the existing Close action. When the interaction feature is enabled, the Home controls route new messages and interrupts through the conversation.

The browser keeps the random intent reference for that exact session and generation in tab session storage. A dropped response or a reload recovers only the receipt for that intent and login. The panel distinguishes a delivered interrupt from a confirmed end of the target turn. It shows the queue pause and pending count from the same receipt snapshot. An explicit resume preserves the historical interruption result.

Migration 177 links a new interrupt to the exact operation and stream proved during admission. Confirmation requires the committed terminal event for that native turn and a matching canonical terminal receipt. Core can keep the interrupt's own receipt at SUBMITTED after delivery. That receipt and the original turn's matching terminal proof allow explicit resume without recording a different control outcome. A pending, reconciling or otherwise unconfirmed interrupt retains the barrier.

## Evidence

- The combined Python run passed 124 cases. It includes the authenticated exact-target, barrier, receipt recovery and resume integration, the R4 send-cut regressions and SQLite migration tests. A subsequent run of both targeted dashboard cases passed against the final route changes.
- The migration test upgrades a seeded schema 176 database, preserves the existing interrupt, pending message and pause, leaves the new link table empty, and passes the foreign key check. A second application is a no-op. The earlier migration set refuses schema 177 and leaves the records intact.
- The production frontend build and all 412 Node tests passed. The offline wheel and source archive passed Twine's strict check. Six files, including migration 177, the receipt projection and the dashboard bundle, matched their source bytes. The temporary wheel has SHA-256 `bb3a1864ec4e16d8fe5871db08051a88e908ee3f97e4e8c4841d5b65e6932870`.
- Playwright drove headless Edge against the built app, temporary SQLite store and synthetic Codex peer. The browser declined the first review by keyboard. It submitted one interrupt, lost the success response and recovered the original receipt after reload. At that point the panel showed one pending message and reported delivery without confirming interruption.
- The fixture then emitted the terminal event for the original native turn. The panel reported “Turn interrupted” and the queue remained paused. Explicit resume dispatched the original pending message once and retained both confirmations after a refresh. The synthetic peer received the initial turn, one interrupt, then one resumed send. The technical view showed only Close as a runtime action while the interaction gate was enabled.

## Delivery and rollback

The interaction flag remains opt-in. Once schema 177 is applied, rollback needs a schema-aware build that preserves the target link, pending inputs and durable pause. Controls created before schema 177 keep their receipts without an inferred target link. A submitted control with no retained terminal proof stays unconfirmed.

Realtime native qualification, Pi and Claude observed-run targeting, reorientation, and human accessibility validation remain open. The browser and server were temporary and used no provider account.
