# P11 — current operator guide and fresh suite inventory

Parent `e9bbd09`, branch `feature/v0.2.0`, 2026-09-23. No runtime contract change
in this documentation unit. Schema054/surface42/identity9. Final gate NOT PASSED.

The operator guide previously carried historical instructions below an interim
warning: implicit Agent upsert, inherited provider configuration, live callback
delivery, unrestricted pull after push, TTL-based relay and broadcast results.
Those no longer describe production composition. The guide now explains canonical
identity, approved endpoint/profile setup (including Codex), operator versus scoped
agent authority, durable inbox/outbox, correlated results, bounded explicit relay,
native input and uncertain-operation recovery. Four connectors and their distinct
limits are retained. Capabilities marked not_probed and unfinished recovery/UI/
backup gates are explicit, without reusing old native campaign counts.

Changed file: docs/harness-integrations/operator-guide.md. All five relative links
were checked against the local filesystem using Python pathlib/re; PASS. This is
a documentation update, not evidence of a new native capability. ADR rewrite is
still pending. No provider, personal configuration or interactive session used.

## Fresh regression inventory

Command:

```text
rtk proxy .venv/Scripts/python.exe -m pytest -q --maxfail=10 --junitxml=plans/pr34-remediation/evidence/current-suite-inventory.xml
```

Observed **FAIL**: 10 failed,798 passed,68 skipped,2 warnings in244.74s. The run
stopped at maxfail; the rest of the suite is NOT_RUN. The XML was reduced to
[a durable counts/failure manifest](evidence/p11-legacy-suite-inventory.json),
without copying absolute temporary paths and full fixture traces. No earlier
suite count is substituted for this result.

All ten first failures are in tests/test_harness_target_grammar.py. They call
HarnessSupervisor.open for an unregistered identity and fail at the required
canonical identity check. Inspection also found that this file constructs the
retired synchronous notifier composition and expects implicit profile writes,
unreserved inbox delivery, uncorrelated terminal forwarding and session/TTL relay.
Merely registering its test identities would not migrate the coverage correctly.

Next unit: migrate routing direct/capability/role/tag and failure/isolation coverage
to authenticated production serve, registered Agent/profile/endpoint and durable
operation assertions. Preserve or explicitly map send-only and relay cases to
current P10 tests; do not delete coverage or restore the retired callback to obtain
green results. Then resume the full inventory and diagnose later failures.

PR34 was rechecked with `rtk proxy gh pr view 34 --json headRefOid,baseRefOid,headRefName,state,url`:
OPEN, head d7d87d0c3ee2ea2ed7c63cdb8f9cafdbd5ee0397,
base27b06fe48b9f95b35c94f50827fea83d178f4e12. Remediation remains on the separately
authorized feature/v0.2.0 branch; no merge or PR write was performed.
