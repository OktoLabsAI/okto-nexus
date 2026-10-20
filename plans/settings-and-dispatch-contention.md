# Settings and dispatch contention — 2026-10-16

- [x] Split Settings into Interface, Runtime, Coordination, Security and Storage.
- [x] Preserve mounted drafts across tabs; one fixed save action covers settings,
  runtime policy, one-shot capacity, operator access and browser appearance.
- [x] Guard dashboard navigation/sign-out and browser unload with pending changes.
- [x] Hide settings without implemented consumers (metrics retention) from the
  catalogue; correct obsolete descriptions of implemented coordination features.
- [x] Browser check: switching tabs retained edits, leaving prompted, cancelling
  preserved the page, save cleared the pending state. Runtime screenshot in
  `output/playwright/settings-runtime.png`. Frontend production build passed.
- [x] Settings API: seven unchanged cases passed; the catalogue case passed after
  updating its expectation to omit unimplemented controls.
- [x] Diagnose local runtime containment: at 10:01:26 a retryable SQLite writer
  admission timeout escaped the dispatch pump, invoking host-wide containment.
  Its stopping flag prevented subsequent automatic recovery. Stack and server
  logs captured without native payloads. CPU saturation was observed later;
  the specific transaction holding the writer at the failure was not identified.
- [x] Retry only retryable DB_ERROR at the database boundary, with asynchronous
  bounded backoff. Native sends are not retried. Non-retryable failures retain
  the existing containment behavior.
- [x] Six dispatch tests passed, including contention before reservation and
  before send, unchanged attempt number and exactly one send after recovery.
- [x] Old live instance gracefully stopped with DRAINED and completed shutdown.
- [x] Installed rebuilt Nexus 0.3.1 wheel and verified installed backend files
  and dashboard index match sources. Server PID 15804 started successfully.
  Pi, Claude and Codex all report Ready through `/api/v1/agents`; dashboard
  returns HTTP 200 and settings catalogue omits metrics retention.

Separate endpoints are not one atomic transaction: successful sections remain
saved if a later section fails; pending edits remain available for retry.
No commit or push performed.

## Partial runtime replies and operator form

- [x] Correlate message publications with persisted runtime result outcomes;
  historical interrupted/failed or truncated replies display an incomplete-output
  notice without rewriting the original messages.
- [x] New interrupted/failed publications carry an explicit subject and body
  warning. Preserve the 60,000-byte artifact threshold and successful behavior.
- [x] Operator access uses responsive labeled columns, consistent input styling,
  password mismatch feedback and the shared Settings save action.
- [x] Ten focused presentation/query tests passed. Read-only validation against
  the two actual Pi publications confirmed success versus interrupted metadata.
- [x] Browser layout inspected (`output/playwright/operator-access.png`);
  production frontend and wheel builds passed. No credentials changed.
- [x] Installed `build/partial-results-dist/okto_nexus-0.3.1-py3-none-any.whl`;
  installed backend files and static index match sources.
- [!] Deployment found a separate shutdown issue: four Pi OPEN_PENDING sessions,
  recurring recovery errors and DRAINING_PENDING. Graceful shutdown did not
  complete. After verifying the Nexus process had no children, terminated only
  that verified server process. Logs/stacks retained in
  `build/partial-shutdown-incident`; databases and journals were not reset.
  This restart does not establish a fix for that reconciliation issue.
- [x] New server PID 3596 (launcher 39468) responds HTTP 200. Live message API
  reports the actual Pi replies as interrupted/partial=true and success/partial=false.
  Claude and Codex are Ready; Pi remains Recovering, a separate unresolved issue.
