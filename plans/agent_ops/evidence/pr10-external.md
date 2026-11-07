# PR-10 — External attention and agent activity

This milestone implements OBS-11 and preserves the fixed R3 plan. PR-10 remains
in progress: OBS-12 correlation wiring, joint regression and the declared real
provider/client/native-service campaigns are separate outstanding work.

## Behavior

The operator attention projection now includes `external_blocked`,
`external_completion_unseen` and `external_observation_stale`. These are watch
items with explicit source, generation, report freshness and inferred/explicit
evidence. Their only source action is `inspect_external_observation`; external
reports do not authorize approval, dispatch, permission decisions or completion
of canonical work.

Blocked reports keep their episode across continuous heartbeats. A real state
change, TTL gap, generation rotation, authority change or publisher revocation
creates a distinct episode. Migration 165 adds the episode anchors without
rewriting canonical history. A completion event is retained independently of
the current head; repeated references do not duplicate it, different completions
between refreshes remain individually inspectable, and marking one seen does not
dismiss another. Expiry means unknown activity, never idle/offline. Revoked or
disabled authority makes the observation unavailable.

`GET /api/v1/observations/instances/{id}` performs an exact authorized lookup.
`GET /api/v1/observations/summary` returns the complete authorized aggregate,
including counts by agent, independently of instance-page size. Both reuse the
same current facts and temporal validation, expose bounded refresh deadlines,
and reject unsupported query parameters. Self-managers cannot inspect foreign
instances; publisher credentials cannot read operator data. Public responses
exclude publisher metadata and contain no bearer credentials.

Agents displays external activity separately from presence and capacity. A lazy
instance list uses pages of 20 while the summary remains complete. Inspection
checks source, agent, workspace and generation; a changed selection clears the
old content. Retained completion details appear separately from the latest head.
Source references/reasons are escaped text, without generated links or commands.
The reader coalesces requests, cancels obsolete scopes, enforces a timeout and
monotonic freshness, marks failed/overdue reads stale, and clears protected data
on authorization loss. A forbidden reader needs a new mount/scope before retry.

## Qualification and packages

The initial source reports contain 312 distinct Python cases and the frontend
report contains 121 passing cases. The initial installed campaign passed 158
cases: 155 overlap source coverage and three verify installed import boundaries.
Counts and the renamed frontend test are reconciled in
[`pr10-external/reports.json`](pr10-external/reports.json); overlapping reports
must not be added together.

The initial wheel SHA-256 is
`48eee2b5136f40ed3f37e4df73896d8d4d91bbc064d2cf918d2dfa85c461292d`.
All 672 packaged files match source and installed bytes: 497 Python files, 165
migrations, seven static assets and three other files. It is a non-editable
installation outside the checkout with import guards for Nexus and Core.

The real Chrome campaign used that installed wheel, actual loopback HTTP and
SQLite, and synthetic agents/reports. It verified inspection, two independent
completion episodes, seen preferences, aggregate counts, workspace changes,
expiry, generation fencing, feature toggles, escaped text, and light/dark/narrow
presentation. Network abort and 403 were explicitly injected browser failures;
they are not represented as Server failures. Escape closed the inspection and
restored its trigger. A separate Tab diagnostic was inconclusive and is not an
accessibility acceptance claim. The retained trace includes failed diagnostic
attempts and the initial metrics notice; metrics remained disabled.

The final comparison found all 146 canonical tables unchanged, excluding the
explicit observation/settings/viewing-preference surfaces. The Server stopped
through its canonical owner/generation endpoint; an already-held Windows
process handle confirmed exit, and the TCP listener closed. No process-name
kill was used. Browser artifacts and exact trace resources are in
[`pr10-external/browser/browser-results.json`](pr10-external/browser/browser-results.json).
Private bearer files, databases and user/provider credentials are excluded.

## Measured performance and correction

The initial 1 → 200 → 4,096-instance campaign measured real repository/service
operations and recorded SQL statement counts and database growth. At 4,096,
list/detail/summary succeeded but all 12 attention reads (all, blocked and
completion filters) hit the five-second query budget. A readonly repeat
confirmed the same refusal; no partial snapshot was returned. Profiling found
repeated Python JSON conversion and projection before kind filtering, rather
than an increasing number of SQL queries.

The correction selects relevant head/event keys by kind and scope before
projection, removes a JSON encode/decode round trip and reuses the same temporal
validator. It preserves the five-second limit, authorization, exact episode IDs,
viewing preferences and corruption errors. Sixteen additional tests compare
full/filtered results, callback selection, scope, malformed timestamps and
immutable history. Independent review compared all four changed production
files against the initial detached build.

The rebuilt wheel SHA-256 is
`ed6223c0de0d333e7fd108175d1f15dd0a4e72c8e489782ac9869e0284f9a245`;
its 672 files again match source and installed bytes. The frontend assets are
unchanged from the browser-qualified candidate. Its 81 affected source cases
passed. In the readonly 4,096-instance repeat, blocked and completion filters
passed all four samples (medians 3,180 ms and 3,267 ms); full attention still
exceeded the unchanged five-second budget in all four samples. Its installed
campaign passed 110 cases. A second candidate addressed duplicate projection
between aggregate and page reads with a bounded memo scoped to one relation.
Its nine focused tests passed, but its full-query measurement remained
inconsistent. This memo was subsequently removed; its source and reports are
retained as historical evidence, not as part of the final implementation.

The memo candidate (V3, SHA-256
`a5d040eb7bce0deffdbf24f3506000eb5e493e9f36d8cf2116b7057e57746d7c`)
still passed only one of four full-attention samples at 4,096 instances. Its
filtered reads passed, but that result is not accepted as a consistently
successful full-query measurement. No installed test campaign was run on V3.
The following candidate removes the redundant memo and computes aggregate
statistics and the bounded page in one SQL statement over shared materialized
CTEs. The event cursor remains a separate read. It preserves duplicate checks,
snapshot conflicts, ordering and the five-second deadline, including a final
deadline check after the last callback. Twelve new functional cases replace
the nine retired private-memo cases; the retired source and reports remain
historical evidence. The final installed regression is described below.

The V4 source regression passed all 31 focused cases. The final readonly
measurement on the same 4,096-instance database passed all 24 samples before
any report TTL expired, without renewal. Full attention returned 2,096 matching
items with a median of 3,223.50 ms and a maximum of 3,725.25 ms; blocked and
completion filters had medians of 1,227.25 ms and 1,438.58 ms. The statement
counts were 42 for all kinds and two for either external filter. List/detail/
summary used two statements each; summary counted all 4,096 instances. These
are four samples per operation on this Windows machine, not a general SLO.
No tests, build or browser campaign ran concurrently; light artifact/hash and
documentation work is recorded in the benchmark context sidecar.

The V4 wheel SHA-256 is
`280c0e0cca2b02ae0fa69443ed44889609988f4432af928d839013c2618bf035`.
All 672 package files again match source and installed bytes. Its broader
installed attention regression qualified 292 case identities: 291 passed in
the broad run and the corrected migration case passed in a focused rerun.
Across V1, V2 and V4, installed reports cover 431 distinct case identities;
reruns are not added together. The source reports cover 341 distinct cases
still present in the current tree. Nine retired memo cases are historical
only and are not added to that number. The current UI has 121 passing cases.

The exact retained bytes are enumerated in
[`pr10-external/artifact-manifest.json`](pr10-external/artifact-manifest.json),
including the original failed build log and earlier candidate measurements.
The manifest verifier also checks the Git index bytes before commit.

## Boundaries

- The runtime isolation campaign uses a synthetic native factory with real
  HTTP/SQLite/Core dispatch. External working/blocked/completion reports neither
  submit nor settle canonical operations; only the canonical terminal event
  permits the next queued turn. This does not qualify a real provider.
- OBS-12 currently has only a pure evidence/digest/fence foundation and 91
  passing domain cases. No correlation endpoint, persisted mapping or canonical
  precedence is claimed. Public session correlation remains null.
- Corrupt relevant OBS facts fail the shared projection honestly, including
  full attention reads with observations disabled. Canonical work controls are
  independent; this is not a promise that every attention read remains available.
- The benchmark SSE check exercises the real generator and SQLite in process,
  not a TCP transport benchmark. Initial 1/200 baselines are retained; a page
  limit is never represented as a smaller database cardinality.
- Initial runtime assertion failures, the frontend kind-count assertion, and
  the missing-setuptools build environment failure are retained and explained.
  They are not counted as successful qualification runs.
- Real local/remote M1, real two-client M2, new remote-identity provisioning,
  native Windows lifecycle campaigns, OBS-12 and joint R3 acceptance remain open.

The DX-13 ledger reconciliation is separately supported by historical evidence:
[`pr10-dx13-reconciliation.md`](pr10-dx13-reconciliation.md). It is not a new
provider or PR-10 package campaign.

The broad V4 campaign retained one `FileNotFoundError` in an old migration
test that assumed a source checkout. The corrected test reads SQL through
`importlib.resources` and expects the current migrations through 165, while
preserving its backfill, privacy and immutable-history assertions. It passed
separately on source and the unchanged installed wheel. The original XML,
qualification proof and test bytes remain under `final/initial`; the focused
installed correction is under `final/followup`. No all-green broad rerun or
synthetic merged XML is claimed.
