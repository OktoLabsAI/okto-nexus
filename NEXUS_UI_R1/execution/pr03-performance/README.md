# UI-022 — bounded entries queries and state evidence

Cut: Nexus `c08698f187de50a5101e7cc2f3054aa6061ee7ea`; exact source SHA-256 pins are in `environment.json`. All nine pins were checked again after execution: no drift. No product, index, migration, service, frontend build, ledger, provider or personal database changed for this probe.

Run from the repository root:

```powershell
rtk proxy .venv/Scripts/python.exe -X utf8 NEXUS_UI_R1/execution/pr03-performance/measure.py
rtk proxy .venv/Scripts/python.exe -X utf8 NEXUS_UI_R1/execution/pr03-performance/semantic_probe.py
```

The runner creates separate `nexus-ui022-*` temporary Homes using the existing canonical fixture. The original fixture still owns admission/WSS/lease ingress for its first session; volume rows are explicitly **synthetic persisted read facts**, not new admitted executions. Each measured workspace has N distinct agents/endpoints/bindings/sessions and ten direct SUBMITTED turn facts per agent. The largest case adds 100,000 vocabulary-valid synthetic workspace events (100,002 total including the fixture baseline). Nothing invokes a native binary, provider, browser, host service or personal authentication. Synthetic event volume tests log bounds, **not** event replay or transcript ingestion.

## Observed service latency

Twenty sequential measured reads per series, one explicit unmeasured warmup per series, `perf_counter`, median p50 and nearest-rank p95. The first initial read is reported separately in each raw file. JSON payload sizes use compact UTF-8 encoding. These are `HomeEntriesService.read` timings, **not HTTP, UI, network or production SLO measurements**. The Windows host was shared: Root ran TypeScript and a real-fixture HTTP pytest in parallel during this period. CPU, disk and cache were not exclusive; isolation applies to DB/Home/provider use. No latency samples were discarded or retried.

| Agents / activities / events total | Groups p50 / p95 ms | Children p50 / p95 ms | Max groups / children bytes |
|---|---:|---:|---:|
| 1 / 10 / 2 | 182.20 / 225.95 | 227.22 / 279.88 | 7,465 / 12,761 |
| 10 / 100 / 2 | 315.95 / 393.37 | 306.79 / 341.44 | 62,611 / 12,763 |
| 100 / 1,000 / 100,002 | 718.42 / 1,225.94 | 826.57 / 1,031.41 | 63,170 / 12,770 |

All measured envelopes were `ready`, all seven source statuses `ready`, and initial totals were exact. The large case **does not meet a 500 ms target**, even at p50; this evidence must not be promoted as target attainment. All cases remain below the unchanged 5-second service deadline in this sample. The first-ever read includes a different cache/context state; twenty warm reads do not characterize cold-tail latency.

## Query and pagination boundaries

Each size's separate instrumented initial-page read issued **55 SQL statements, one `write=False` UoW, zero database changes**. Statement counting includes nested authorized reads and temporary read-side materializations. No event-journal/transcript source was queried. SQL text, six live-context `EXPLAIN QUERY PLAN` captures and every raw latency/payload sample are retained in `agents-1.json`, `agents-10.json`, `agents-100.json`.

There is no observed SQL-statement increase per agent for this initial-page workload. This does **not** mean O(page) work: every continuation reauthorizes and recomputes the complete authorized relation and material revision. Source assembly is bounded O(N + relationships), with a 100,000-row source cap and 5-second deadline. The large plans include scans, materializations and temporary B-trees for sorting, grouping, distinct and unions. Constant statement count does not imply constant rows, CPU or latency. Instrumentation was separate from timing; expansion series were timed without the trace callback. The source/read scheduler, rather than a second frontend merge, drives expansions.

Full group pagination covered exactly 1/10/100 unique groups in 1/1/10 pages. Each sampled group has ten exact children: initial preview three plus seven on its own continuation, no duplicates and no remaining cursor. Full-pagination coverage is a correctness check, not an aggregate traversal latency percentile. No new index was proposed: T-PERF-03's conditional new-index EXPLAIN/write comparison remains not exercised; existing EXPLAIN alone does not qualify a migration.

## Semantic scope

`semantics.json` records three actual assertion groups through the new entries service against real SQLite:

- The same agent's started second session is `running`, while its original exact session is `awaiting_operator`, with different stable entry IDs. Productive running requires the synthetic canonical `delivery_phase=started` ingress fact and matching stream/generation, rather than a READY lease or receipt alone.
- Additional READY and OPENING sessions without a turn remain passive exact session context, with no invented operation ID and no productive running. Across all volume datasets, SUBMITTED turns without started ingress display only `native_accepted`.
- CLAIMED remains `claimed`, uncertain remains `outcome_unknown`, and SUCCEEDED plus requested containment remains `result_available_cleanup_pending`. These read states do not dispatch retries, finish/verify a handoff, or grant native controls.

This is SQLite/domain projection evidence, not a real native execution campaign. Warm-lease lifecycle permutations and linked success/handoff cleanup are not newly exhaustively qualified here; existing semantic tests remain separate evidence. Neither unknown/cleanup nor missing native support was relabeled success.

## Exit and reproducibility

The full measurement process exited **0** (tool session 43506, final poll `e1efd6`); the semantic probe exited **0** (session 71327, poll `463ba7`). Shared fixture context managers exited normally and closed their WSS/lifespan generator and connection factories before writing PASS. No child server/browser/provider process was created. Temporary DBs were retained only in the explicit own temporary directories recorded in the raw reports; they are not repository artifacts. The earlier two-sample 1-agent smoke was replaced by the complete twenty-sample raw run; only the latter is used above.

`qualification.json` is a conservative outcome, with SHA-256 of the scripts/raw evidence. It records the performance miss instead of declaring UI-022 fully verified.
