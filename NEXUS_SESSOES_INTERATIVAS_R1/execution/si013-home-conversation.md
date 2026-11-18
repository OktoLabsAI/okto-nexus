# SI-013 conversation in Home

Home inspection opens the conversation for the exact owned session, including sessions without an operation. The output terminal and existing runtime controls remain available in Technical activity. Legacy session inspection retains the existing output view when generation is unavailable. Interaction metadata returns the current stream epoch so the UI can detect a changed transcript while paging. Conversation history uses the existing scoped endpoint and displays partial history and gaps.

The composer sends ordinary text as a native next-turn input. Enter sends, Shift+Enter inserts a newline and composition events protect IME typing. The composer keeps the draft and client intent in memory for the exact scope and owner generation, and clears them when the human login expires or changes. The user can sign in from the panel and return to the same session. The UI and API reject a leading slash or bang in ordinary input. Native commands require the separate command path planned in SI-016.

After an ambiguous send, the draft stays visible and the submit button is disabled. The receipt action reads the original intent. A receipt that is still missing leaves the send uncertain. Queue acceptance and dispatch are shown separately from confirmed native transcript messages.

## Evidence

- The dashboard frontend build passed. All 410 Node tests passed, including embedded conversation and technical views, generation and epoch checks, and message reconciliation.
- The focused Python suite passed 33 cases covering runtime input, transcript and contracts. The dashboard input regression includes rejection of command prefixes without returning the text.
- Playwright drove headless Microsoft Edge against the built dashboard, real loopback application routes and a temporary runtime database with a synthetic Codex peer. The browser opened the exact Home panel and displayed the committed fixture reply. The user signed in inline and stayed on the same session. Enter left the slash draft in place. A multiline draft survived a round trip through Technical activity, which showed the existing terminal and controls.
- The fixture committed the input and dropped the first POST response. The browser retained the draft, disabled submit and offered the receipt action. One receipt GET recovered the original dispatching state. Fixture counters recorded one accepted POST, one queued input and one native dispatch. The UI reported “Sending to the harness”. The run used no provider account. The temporary browser and server were stopped.

## Delivery and rollback

The interaction gate remains opt-in and the existing database schema is sufficient. A draft is lost on full page reload. A read-only receipt lookup remains available through the API if the original intent is known. Turning off the interaction gate disables new composer submissions. A source revert restores the previous Home inspection and leaves durable records in the database.

SI-013 remains in progress. Exact-session switching with a draft, full plan scenario coverage, real harness acceptance and human accessibility validation still need evidence. SI-014 adds queue visibility and explicit queue and runtime controls.
