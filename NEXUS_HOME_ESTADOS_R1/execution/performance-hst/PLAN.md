# HST027 — prepared controlled comparison (NOT EXECUTED)

Wait for Root's `PACKAGE_READY` and an exclusive benchmark window. These scripts
have not generated a dataset, imported a product runtime, or measured latency.
Source-global regressions currently retain their input freeze. No prior
performance qualification is inherited.

Baseline: frozen installed i4 Nexus 0.3.6, wheel
`d2c322168d56e87bde22cfe262d5d2fbc9a5737b0572144774894624d561cf88`.
Its READY file is `NEXUS_QUICK_CONNECT_R1/execution/qc36-final-package/READY.json`.
The fresh 0.3.7 candidate READY/wheel/prefix will be supplied after build. Never
install/reinstall into either prefix. Every worker runs its selected Python with
`-I -B`, from its own Temp cwd, with no checkout product path.

## Dataset and comparison

Generate once under baseline from the existing finite, inert Home fixture; only
test helper sources are dynamically loaded. Then add clearly synthetic SQL read
facts in a separate workspace. They are benchmark rows, **not** real runtime,
grant/admission, native pause/resume or provider qualification. No productive API
is invoked on these copied facts. The builder emits no database/keys into Git.

Three cases: 1, 10, 100 distinct registered connections, 10 activities per
connection (10/100/1000). Largest case adds exactly 100000 historical native
ingress events with bounded synthetic payloads and consistent stream watermark
rows. Smaller cases have no added history. Record native ingress separately from
the seed fixture's generic event table; do not silently call both the same count.
Connections share a host but have distinct full binding/workspace-binding/agent
and endpoint identities. The mix includes terminal/no-pending, running, queued
and unknown metadata, explicitly synthetic. No private content or personal data.

Close fixture/database before cloning each seed home into **three** distinct
homes: baseline v1, candidate v1, candidate v2. Record file/dataset hashes, schema
hash and foreign-key check; clone DB SHA must match exactly before bootstrap.
Candidate migration/schema differences stop comparison for review rather than
silently treating changed data as identical. Each variant reads its own copy;
no SQLite DB, UoW, cache, source prefix or process is shared between variants.

Run sequentially in fixed order for each case: baseline v1, candidate v1,
candidate v2. Same machine, Python/SQLite/dependency metadata, clock, dataset,
query scope, page size 10, preview 3 and test-helper source hashes. Compare v1→v1
for compatibility cost; v1→v2 measures the new presentation's total cost, with its
additional metadata/semantics clearly identified. Not a statistically randomized
experiment; machine load/order/cache limits remain recorded.

## Metrics and instrumentation

Real ASGI HTTP GET through installed app/router/auth/serializer, without lifespan
or background runtime. Own loopback operator context, no agent impersonation or
personal credentials. This excludes TCP/TLS, browser layout and first paint.

For root overview and a selected card's first activity page:

- First response separately, 3 unmeasured warmups, then at least 20 samples.
- Record every elapsed sample/status, p50, nearest-rank p95, max and payload bytes.
- Repeated root GETs are refresh cost; capture revision stability and refresh
  deadline without repeatedly changing the fixed evidence clock.
- One separate instrumented read counts SQL statement opcodes and UoWs/writes;
  never stores expanded SQL, bound parameters or response content. Query-growth
  comparison across 1/10/100 detects per-card fan-out. Optional EXPLAIN query plans
  contain only table/index/plan descriptions, with no parameter values.
- Hash productive tables before/after reads. Existing auth bookkeeping is
  distinguished from grants, claims, queue, sessions, native operations/decisions,
  receipts, outbox and setup commits.
- Verify three installed module origins and all package payload bytes before and
  after. No provider/CLI subprocess is allowed inside worker; no network socket
  connection is allowed. Temporary DBs/logs stay in the explicitly owned Temp root.

Targets remain **2 seconds first useful view** and **500 ms p95 read**, alongside
any stronger existing target. HTTP first-response timing is only a proxy for
server readiness, not proof of first useful DOM; browser first-useful-view is
NOT_RUN until measured separately. A fast partial/error response is not a passed
latency target. Missing samples/timeout/failing readiness remain unqualified.
No single-sample p95 claim. Report a miss and retain raw samples; do not erase the
target or adapt data to make it green.

## Safety, limits and stop conditions

Only new own Temp roots may be created. Require explicit `--released PACKAGE_READY`
at execution time; no invocation is included in this preparation milestone.
Workers refuse output overwrite. Each measured case has a 180-second budget;
orchestration should bound its single owned worker to 240 seconds, record timeout
and preserve data rather than retrying automatically. Worker subprocess creation
is forbidden, so no provider/native child tree is possible. Root controls the
exclusive timing window and any later cleanup; no recursive delete is prepared.

Pending product delta identified during preparation: Root has accepted extra
batch fences against current authorization/configuration/credential revisions and
the realization's exact workspace binding. Those corrections await
`READERS_RELEASED`; this benchmark will use the final package after them. They
are not implemented or measured by these scripts.

Prepared files: `dataset.py` (synthetic generator), `benchmark.py` (build/measure
workers). Orchestration/release and candidate prefix are intentionally pending.
