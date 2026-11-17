# R7 read-target failure and correction scope

The original **500 ms read p95** and **2 s first useful view** targets remain.
The R7 matrix measured ten cuts, with twenty samples per route after three
warmups. Five of eight candidate cuts passed the read target; three failed.
Both baseline cuts failed separately. The current candidate is not approved
against the read target and no target is waived. See
`persistent-r7-final/qualification.json` and its raw per-route samples.

The mixed100 candidate V2 p95 is 876.423 ms for overview and 927.279 ms for the
activity page. OPEN100 V2 measured 497.934/489.176 ms, with a very small margin;
one series does not establish reliability or production capacity. Mixed V2
overview is 29.06% slower than the paired baseline in this window, while OPEN
V2 is about 43% faster. Earlier series remain immutable, including the slower
R6 mixed cuts. Do not describe this as a general performance win.

The separate three-GET R7 diagnostic proves that the result-attention fast
path ran: 925 index projections, zero legacy result-attention UDF calls and
no correlated scalar lookup in the batch SQL. This is not an unused-fast-path
problem. The SQL-only observation attributes 350.455 ms to execute/fetch of
the combined Work/Results statement. Its cProfile counterpart records
705.061 ms in complete relation reading, 390.610 ms in board composition,
224.940 ms in canonical serialization and 135.256 ms in material revision.
Those cumulative costs overlap and must not be added. A third GET reports
1133.992 ms in the service and 1156.805 ms in HTTP; blaming transport does not
explain this steady observation. Diagnostic GETs are not p95 samples.

The next correction must stay within the Home read model, owned by Codex:

1. Separate the minimal facts needed for complete authorized correlation,
   grouping, counts and revision from repeated presentation transformations
   in the combined Work/Results query. Profile the existing activity/result
   JSON UDF and materialization steps independently before choosing a change.
   Hydration may be deferred only after the backend has the complete scoped
   inventory; it must preserve exact targets, proof, content availability,
   retention, permission filtering, source budgets and cursor invalidation.
2. Inspect request-local duplicate canonicalization of immutable correlation
   context and revision inputs. A derived value must not survive its read,
   principal or source revision. Preserve the current complete-revision
   equivalence oracle, including equal IDs, changed nested metadata,
   malformed values, expiration, partial sources and custom query ports.
   No cross-request authority/freshness cache or Attention engine rewrite is
   justified by these observations.
3. Measure an isolated prototype against both mixed and OPEN datasets before
   adopting it. Reject changes that merely reduce query count, hide rows,
   drop proofs, truncate to first pages or move unbounded work to React.
   Do not promise that one local optimization will reach 500 ms.
4. An adopted source change requires new focused equivalence tests, source
   and installed regressions, a fresh frozen wheel, functional browser
   revalidation and the same exclusive paired matrix. Never overwrite the
   R7 prefix, seeds, helpers or reports, and never change the target to obtain
   a pass.

The prepared large-DOM experiment remains a separate measurement with a
disclosed synthetic clock/fact dataset. An actual useful-DOM observation is
required; the ten successful first-HTTP proxies do not substitute for it.
Native campaigns, AT and human acceptance remain independent gates. No
schema migration, Core/Connector/protocol change or default rollout is
authorized by this correction plan. Its state is **OPEN, not implemented**.
