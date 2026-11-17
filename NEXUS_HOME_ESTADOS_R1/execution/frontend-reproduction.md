# HST-004 — frontend reproduction and proposed boundary

Status: **defect reproduced; no product fix and no scenario qualification**. The controlled Node run contains two passing diagnostic/control tests and one deliberately failing acceptance test. This is the unit portion of HST-T-F01 only. It does not complete HST-004's J1–J8 fixtures or F01's browser requirement.

Reviewed the supplied plan §§7/9, HST-018–023/026 and F/G/J scenarios; current CONTRIBUTING and CI; controller/hook, operational composition, harness activity panel, entry/session selector, exact-session reader and existing controller tests. Exact source bytes are pinned in [source-pins.json](frontend-reproduction/source-pins.json); command/exits are in [run.json](frontend-reproduction/run.json), with literal output in [node.log](frontend-reproduction/node.log). The scripts live only in execution; frontend sources/canonical tests were not modified.

## Reproduction

The script reuses the existing `uiHarnessController.test.mjs` fixture definitions and `homeR1Support.mjs` fake clock, importing the actual transpiled `HomeController`. The board API returns the same valid fixture each time; no DTO or authority is supplied to a real backend.

1. Configure the harness-family controller and complete its first snapshot.
2. Pause presentation, matching the effect triggered when OperationalHome opens a panel.
3. Advance two 15-second fallback polling intervals. After each, request the existing card's child page.

Both cycles produce `paused=true`, `hasPendingUpdate=true`, an identical visible snapshot, `status=ready`, `error=null`, empty stale sections, and **zero child reads**. Three board reads occur (initial plus two polls), with peak concurrency one. Before the first poll, the same paused child-page request succeeds and appends `work2`. Therefore pause alone does not block the child method; the identical poll's pending flag introduces the regression.

The expected contract test fails precisely on:

```text
actual:   { pending: true,  childReads: 0 }
expected: { pending: false, childReads: 1 }
```

Node exits 1, intentionally preserved. All 12 source pins remain unchanged. A prior orchestration attempt never launched Node because Python rejected simultaneous `stdin` and `input`; the subsequent run's source-pin reader compared a hash with its metadata object. Its actual Node red result is retained under `antecedents/pin-reader/`; the final runner reads the `sha256` field correctly. These instrumentation failures are not product failures or accepted scenarios.

## Concrete code path

- `OperationalHome.tsx:108` invokes `pause(manualPause || !!panel)`.
- `homeController.ts:250` schedules the existing 15-second fallback even while presentation is paused, which is desirable for current facts.
- `publishHarness`, around line 518, sets pending whenever `state.paused` is true, without testing whether the accepted snapshot changed semantically.
- `loadHarnessChildren`, around line 229, returns whenever pending is true.
- Local `HarnessActivityPanel` at `OperationalHome.tsx:37` derives `stale` from that flag; both exact-entry buttons and pagination become disabled. It explicitly tells the user to close/reopen.
- The outer `blocked` around line 168 also combines paused, loading, pending, source state and errors; it disables unrelated card reads. Apply updates is disabled while a panel is present, around line 187. This forms the close/reopen dependency described by the plan.

The existing controller test proves paused child pagination only **before** a periodic identical snapshot arrives, so it misses this boundary.

## Minimal implementation proposal for HST-018/019

Retain the existing one-in-flight scheduler, abort/generation fences, fallback/TTL and shared shell stream. Separate current canonical cache, displayed board/order and exact detail interaction; do not add polling/streams per card.

`hasPendingUpdate` should mean a semantic delta awaiting presentation. An identical paused snapshot must update observation bookkeeping without setting it. Prefer the agreed semantic revision contract; do not blindly ignore all clock/heartbeat fields, because a real validity/coverage transition must still invalidate eligibility. Freshness, source coverage, item identity/placement, counters and relation revision/cursor changes matter. A new generated timestamp alone must not announce a result or reset pages (F03/J06).

Use separate gates: (1) an exact known target may start a read that revalidates current authorization/identity; (2) pagination requires the current revision of that relation, with conflict causing a first-page reread **inside the same panel**, never append across revisions; (3) mutations retain canonical recipient/revision/validity checks and explicit idempotent intent. A partial unrelated source cannot globally forbid an otherwise authorized native read. Normal refresh belongs to notice/status, not persistent error/alert.

Keep paused order, focus, scroll and drafts stable while the canonical cache advances. Keep the selected identity independent of its column. Do not replace a form's reviewed decision revision with a new snapshot's revision. Preserve immediate clear/abort on 401/403/logout regardless of pause; the controller and `HomeSessionInspection` already contain useful clear/listener behavior to retain.

## Selection and fewer steps (HST-020/021/023)

Use an event's exact target first. For a harness card, open one eligible session directly only when the **complete authorized relation** proves uniqueness. Preview length one, unknown total or `has_more` cannot prove that. Multiple sessions use a short selector in the same panel; no active session opens passive connection/history without starting runtime.

Current `initialEntrySession` correctly prioritizes explicit session-bearing targets and never selects by recency; its fallback uses `sessions_total===1` and one item. Reconcile completeness/eligibility with the frozen backend DTO rather than infer eligibility from four IDs. `HomeEntryInspection.tsx:74` currently labels options with session/workspace/executor IDs; add authorized objective/state/project/time metadata for readable options while retaining full IDs in detail. `homeSessionInspection.ts` already checks all seven canonical context fields and can be reused. Preserve dirty-transition guards and one active viewer, without nested modals or creating a PTY.

Compact the project/Add/summary header and keep all three columns. Move unavailable Reconnect into detail; never substitute opening context for runtime reconnect. Reuse canonical Handoff/Message for task/conversation labels rather than classifying text through a model.

## Remaining evidence and gates

F02–F14, G01–G08, J01–J06 and HST-026 are **not executed** by this reproduction. Next focused tests should cover same revision/new timestamp, real validity expiry, changed relation/cursor recovery, auth clear during pause, a real revision while a draft is edited, independent-source failure, exact selection under movement, and focus/history. Browser, 360px/native zoom, keyboard and real AT remain distinct later qualifications. No performance percentile, backend query count, human comprehension, provider execution or authority transition is inferred from Node timing.
