# SI-016 session commands in Home

Typing a slash in the conversation composer shows the exact-session catalogue. The list filters by command name or label. Selection prepares the command and shows its effect. Send requires a separate confirmation. Steer and interrupt open the existing exact-target review and confirmation. Help and status are identified as Nexus actions. Unavailable commands show a reason. Slash paths, unknown commands, and shell prefixes stay in the editor without sending. The composer has no literal override.

The typed command endpoint accepts only the declared Nexus handlers. The original queue, grant, target, consent, and idempotency checks remain in the canonical services. New effects also verify the catalogue revision within their admission transaction. A stale command is refused before admission. A retry can recover a matching existing receipt. Validation errors omit submitted argument contents.

## Evidence

- The backend regression passed 95 tests. The integration accepts typed help, status, next-turn send, steer, and interrupt. It verifies rejection without affirmative confirmation, with stale catalogue revisions, and with arbitrary command IDs or argument fields. A stale interrupt leaves the queue running. The integration uses the synthetic native peer and the same canonical controls used by the ordinary dashboard.
- The frontend suite passed 415 tests and the TypeScript and Vite build succeeded. Headless Edge exercised selection without execution, typed status, unsupported and native-only commands, ordinary Enter gating, explicit next-turn enqueue, exact steer review/cancel, a stale steer with the draft preserved, a new successful review, and interrupt review/cancel/confirm with the queue paused. The HTTP trace contained status 200, send 202, steer 409 and 202, and interrupt 202 under the typed endpoint. There were zero ordinary input POSTs and one synthetic native steer and interrupt. A 360px viewport had no horizontal overflow in the command picker.
- Focused Ruff, the offline lock check, and Git diff checks passed. The changed line in the existing app middleware did not change its baseline lint findings. Both archives passed strict Twine checks and the bundled HTML, JavaScript, CSS, and command endpoint matched source bytes. Temporary wheel SHA-256 `424625dce5f9fcaa8199ec639d6897a60161c9a28b2435b7fa7b3d2fe61e3a4e`.

## Delivery and rollback

This increment has no storage migration or Core or Connector pin change. Rollback to the previous build removes the picker and the typed execution endpoint while preserving the standard review, queue controls, and durable receipts. The ledger keeps native terminal transitions, real literal capability and cross-harness qualification pending. The Edge exercise used an isolated database and a synthetic native peer. It did not use a live harness, screen reader, or human participant.
