# SI-014 Home reorientation review

In a supported managed Codex session, the conversation lets the author review a draft for the current turn or review moving their own queued message into that turn. The review holds the exact scope, target, effect, and revisions until confirmation. It shows the draft or the author's bounded queued excerpt and focuses Cancel review first. Enter in the ordinary composer remains a next-turn action when that composer is available.

The receipt distinguishes reorientation from ordinary dispatch and submission from confirmed harness acceptance. If a response is lost, the browser queries the original receipt by client intent or owned input ID. A tab retains the opaque receipt reference across reload, scoped to the exact session and operator. Draft text stays in memory. When the turn changes before admission, the draft remains editable in the open tab and nothing is sent to the next turn automatically.

## Evidence

- The focused backend suite passed 95 cases, including receipt origin, direct and promoted effects, scope, delivery recovery, and ordinary queue interoperation. The frontend suite passed 415 tests and the TypeScript and Vite production build succeeded.
- Headless Edge with the actual Home bundle, isolated Nexus database, and a synthetic Codex peer verified keyboard focus, cancellation, an ordinary next-turn enqueue, and separate direct and queued reorientation confirmations. The fixture dropped both success responses and the browser recovered the original outcomes by GET. When the original turn ended between review and confirmation, the server returned 409, the draft remained editable, and the browser sent no fallback request. The fixture recorded one ordinary enqueue and exactly two native steer calls.
- A second Edge run with the packaged bundle reloaded after direct admission with receipt reads blocked. Restoring network access and checking the receipt showed the original submission, with one control POST and one native steer. Tab storage contained only the receipt kind and opaque intent reference.
- Focused Ruff, diff check, and the offline lock check passed. The 0.3.8 wheel and source archive passed strict Twine checks. The packaged HTML, Vite bundle, and dashboard API matched the source bytes. Temporary wheel SHA-256 `ff206272b786d2eeb18031aa7fd5c1718b10aca088dc6863a845b812f2247e9e`.

## Delivery and rollback

The change stays behind the existing session interaction gate and adds no migration. Roll back to the preceding schema-178-compatible build to remove the Home review while preserving durable receipts. SI-014 remains in progress pending live harness qualification and the remaining cross-harness acceptance evidence. The browser used a synthetic peer. No live harness, screen reader, or human participant was used in this increment.
