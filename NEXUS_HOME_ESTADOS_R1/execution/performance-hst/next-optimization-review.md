# Offline optimization review after R2

This is a read-only proposal, not a measurement or authorization to change schema. The existing diagnostic EXPLAIN/cProfile cut is R1 (wheel `15cc6dfc…af7`), not an R2 profile. Current source was inspected as text only. The original twelve cuts and fourteen persistent cuts retain their failed 500 ms target at 100 connections. No new application import, query benchmark or runtime was executed for this review.

## Smallest concrete SQL candidate

`sqlite/home.py` FACTS still computes `observed_running` with a correlated `EXISTS` over `execution_event_ingress` for each eligible operation. The recorded FACTS plan (`6be2eb63…a8d2fa7`) shows:

- id381: correlated scalar subquery121;
- id388: watermark lookup by full session/epoch key;
- id399: ingress primary-key search by server/executor/session/epoch and `sequence<?`;
- the operation ID and delivery phase remain JSON predicates after that sequence range lookup.

The operation/phase predicate is unchanged in R2. In the OPEN workload, all 1,000 operations are nonterminal; each connection has ten operations but history events identify only its final operation. Therefore nine operations per connection cannot match those history rows and may each traverse the same session/epoch range. This repeated work is supported by the query structure and the recorded plan; its exact R2 wall time is not measured separately.

Propose a statement-local `progress_keys` relation, grouped once by the exact authorized session/epoch/operation tuple from the complete scoped operation relation. Read only contiguous, gap-free admitted ingress and retain the exact started/progress predicates. Join this relation back to operations rather than re-running the ingress range search for each operation. Preserve terminal-result exclusion, owner-generation fencing and every existing authority/currentness condition. Do not cache across UoWs. A successful transformation should visit relevant history once per session/epoch rather than once per operation.

First qualification must compare complete FACTS rows and resulting revisions against the old query on mixed/Open datasets, two epochs, an event beyond the contiguous watermark, a gap, wrong operation/session, terminal result, duplicate progress events and irrelevant history. Then inspect the new EXPLAIN and measure the same clones/targets under a separately authorized window. This proposal is not a claim that it will reach 500 ms.

**Currentness prerequisite discovered during browser review:** `projected_through` is never written by the canonical event producer, despite being read by FACTS and the operational readiness reader. `commit_execution_events` projects results/native requests and commits `committed_contiguous` in the same transaction. Resolve this proof mismatch explicitly before copying an obsolete `projected_through` condition into a new optimized relation. Keep performance and correctness changes separately traceable.

## Index decision

The ingress primary key is already `(server_id,executor_id,session_id,stream_epoch,sequence)` (migration066). Migration157 adds only an error-event partial index, which does not cover turn progress. An operation-ID expression index could address the post-range JSON predicate, but the schema has no `json_valid(payload_json)` constraint. Building a plain JSON expression index could reject historical malformed payloads and adds write/storage cost. No new index is justified as the first change while a no-migration grouped relation can remove the repeated scan. Do not add a generic workspace/index simply because the old plan contains SCAN: several scanned relations are intentionally materialized or already fully scoped.

## Lower-priority Python work

R1 profile recorded `group_id`1,340 calls/18.6 ms and `entry_key`2,401 calls/18.5 ms. Current pages and board still derive these repeatedly; local per-call memoization could preserve exact bytes/order, but this magnitude alone is insufficient to explain the remaining 140–337 ms excess in the R2 v2 persistent cuts. R1 revision/asdict timing is stale after the R2 shallow-snapshot fix and must not be presented as a current hotspot.

Home pages also build a full grouped page merely to supply the harness board's base metadata. A dedicated internal metadata path might avoid redundant sorting, but it is a broader refactor than the ingress relation and requires complete envelope/cursor/expiry equivalence tests. Avoid cross-request fingerprint caching or dropping complete-relation hashing: both risk hiding authorization changes or stale pagination.

The R2 combined Work/Results statement still obtains canonical Attention separately for the occurrence relation; eliminate no policy evaluation or authority check based solely on the earlier R1 repeated-CTE profile. A fresh R2 phase profile would be required to prioritize this over the demonstrated ingress range pattern.
