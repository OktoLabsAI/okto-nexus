# PR-07 — integrated operator attention

Attention now has a dashboard entry, a workspace-scoped active badge, filtered
Needs action/Watch groups and direct canonical inspection. Seen and snooze are
separate viewing preferences. Existing Graph, Meta-harness and specialized pages
remain available. No productive command is added to the attention API.

The client serializes reads and preference writes, batches SSE invalidations,
refreshes at bounded deadlines without requiring new events, and discards old
scope responses. Lost mutation responses are reconciled without replaying the
write. Pagination conflicts discard the stale cursor. Network failures retain
the last authorized snapshot; forbidden/disabled states clear cards, badge and
inspection. The badge uses workspace scope; page filters use their own exact
counts, explicitly separate from that badge.

Exact source references open shared approval/question, handoff verification,
message, execution and maintenance controls. Generic decisions carry the reviewed
decision revision, and handoff verdicts carry the reviewed claim epoch. Unknown
outcomes expose inspection rather than automatic retry. Drafts survive ordinary
polls and transient detail-read failures. An uncertain detail read disables the
form until it is revalidated; confirmed source revisions invalidate old drafts.
Confirmed decisions clear the modal's captured-change guard, while edits made
after a command checkpoint remain protected.

## Qualification

- **100 frontend tests passed**, with zero failures/errors/skips on the final
  source. Directed suites overlap this total: controller 23, navigation 16,
  presentation 11, API 4 and modal-change guard 6. They must not be added again.
- **10 installed backend contract tests passed**, zero failures/errors/skips,
  outside the checkout. These are a focused regression for this frontend-only
  milestone; the larger backend qualifications remain in PR-06 evidence.
- `tsc -b && vite build` passed. Vite retains its large-chunk warning; the final
  JS is about 1.31 MB before compression. No new bundler threshold is claimed.
- The final wheel contains exactly **478 Python files, 163 migrations and seven
  static assets**, with matching sets and raw bytes in source, wheel and installed
  package. All seven assets were also fetched through a real installed HTTP
  Server and matched their wheel hashes. Page/summary, initial metadata-only SSE,
  feature off/on and graceful `DRAINED` shutdown passed.
- Final wheel SHA-256:
  `0beddc66e957af5dcddaeb5fc0a6e13a03e5903ef845a8d1b4734b01d19849d0`.
  No Core/Connector source or version changed in this milestone.

The [report manifest](pr07-attention-ui-reports.json) contains exact test counts
and artifact hashes. Initial
reports are retained, including the two failing source-loss cases that exposed
a stale-status delay during an in-flight preference write. The corrected
controller marks the snapshot stale immediately and does not replay the POST.

## Browser evidence

Real Chrome used disposable Servers, SQLite databases, homes and synthetic
canonical work. The root campaign exercised mixed groups/counts, seen/snooze,
the snoozed filter, reload persistence, exact message inspection, handoff
verification and a real concurrent generic decision. The old generic approval
revision received 409 and reloaded the rejected source. A canonical handoff
Pass sent `claim_epoch=1` and reached COMPLETED after confirmation.

Read-only database hashes confirmed that seen/snooze left all 32 compared
approval/message/delivery/handoff/operation/result tables unchanged. Runtime
heartbeat, inventory and lease activity continued independently. A result card
removed after marking seen returned focus to another card; closing an inspection
whose original card disappeared returned focus to the Attention heading.

The native campaign exercised permission approval, an operator question answered
with `blue`, denial, and real 120-second expiry. Canonical receipts and synthetic
peer wire replies were correlated. Expiry produced no decision or native reply.
The initial modal kept an unsaved-change flag after successful submission; that
issue is preserved in the initial report and addressed by the final regression.
The [final browser report](pr07-attention-ui/final-results.json), on Chrome
156.0.8078.79 and `index-uYo_RvIi.js`, records four passing regressions:
question submission then close, handoff verification then close, handoff draft
retention/recovery after 503, and approval draft retention/recovery followed by
rejection and close. No discard prompt remained after confirmed success. All
disposable campaign Servers ended in `DRAINED` and their browser sessions closed.

Browser-boundary 503/403 injection verified stale rendering and protected-data
clearing; it is not presented as real credential revocation. A real settings
PATCH disabling attention cleared an open inspection and badge, and reenabling
it restored the view. Actual browser offline/online transitions retained the
same episode IDs and restored the live stream. Unit and installed SSE tests
cover gap/reset/burst behavior without history toasts.

Light/dark screenshots, keyboard focus checks and semantic accessibility
snapshots were inspected. At 390 px, the main/document widths remained 390 px.
Long external text containing HTML markup rendered literally, with no created
image or executed script. This is browser/semantic accessibility evidence, not
a claim that a particular screen-reader product was operated.

## Limits and retained diagnostics

- Synthetic peers qualify the UI/canonical contract, not a real provider, native
  external-client campaign, productive M1/M2 or user-service login campaign.
- Navigation tests cover every real emitter/action combination. Unknown-outcome,
  cleanup and executor records were not each separately seeded in the root
  browser instance; their canonical contracts are covered by installed/backend
  and navigation tests.
- The first generic-conflict browser helper used an invalid relative
  APIRequestContext URL and failed before making a request; the corrected
  invocation passed. A quoting error in a read-only focus probe and a stale
  Playwright element reference were corrected by a new probe/snapshot.
- An attempted read-only PowerShell process diagnostic had incorrect nested
  variable quoting and was interrupted. It made no state changes. Explicit
  process inspection after canonical shutdown confirmed the fixture PID absent.
- Initial native-fixture setup attempts had authentication/scope selection
  errors. They were corrected in the Temp helper, without modifying backend
  authority or TTL; their disposable Servers were stopped canonically.
- Imported reports retain their original bytes, including native CRLF and
  whitespace in failure diagnostics; these immutable artifacts are excluded
  from authored-file whitespace checks. All 61 retained artifact hashes were
  compared successfully with their Git-index bytes.
- The staged product whitespace check reports one trailing space inside a
  generated dependency shader string. The identical literal exists in the
  previous committed bundle; authored-file checks excluding generated JS and
  imported report artifacts pass.
  The built bundle is preserved verbatim. Generated JS/CSS/HTML match their
  staged bytes. The unchanged `oktolabs-icon.svg` has a preexisting working-tree
  CRLF versus Git-index LF difference; normalized content matches. The raw
  source/wheel/installed equality claim remains exact.
- The plan, migration history and task/scenario sets are unchanged. Full R3
  remains in progress, including OBS and the previously named real campaigns.
