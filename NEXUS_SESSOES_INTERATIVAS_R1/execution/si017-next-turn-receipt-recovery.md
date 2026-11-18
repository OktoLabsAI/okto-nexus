# SI-017 next-turn receipt recovery across reload

Before a next-turn send, Home saves a single opaque reference in tab storage under the exact session and owner generation. A reopened conversation with the original operator login checks the existing receipt by GET. An unknown outcome holds the send action and allows another receipt check. A received receipt or known refusal clears its reference. Unsent text remains in memory and is not copied to tab storage. Logout and access revocation clear browser state while the server retains its durable records.

## Evidence

- The frontend suite passed 416 tests, including exact session and generation isolation, validation of a stored reference, and scoped cleanup. The TypeScript and Vite build, Git diff check, offline archive build, and strict Twine checks passed.
- Headless Edge used the packaged frontend, an isolated Nexus database, and a synthetic Codex peer. An IME-style composition key event added no send. Shift+Enter inserted a line. Enter submitted the prepared message once. The fixture admitted it and closed the response connection. The editor held the in-memory draft and stored only the opaque intent. After a confirmed browser reload, Home recovered the original receipt automatically, released the editor, and removed the saved reference. The server recorded one input POST, one recovery GET, and one queued entry. A preexisting native turn kept the new text in the queue.
- The isolated browser then expired the operator login through the actual logout endpoint. The live panel and its draft cleared and the durable input count was unchanged. An additional run recovered a receipt for an input that had already reached dispatch.

## Delivery and rollback

This increment changes the browser only. The preceding build still reads the server's existing queue and receipts. No data migration or Core or Connector pin change is needed. SI-017 remains in progress for exact stream, navigation, focus, and accessibility evidence. Browser keyboard events exercised composition handling without an operating-system IME or screen reader.
