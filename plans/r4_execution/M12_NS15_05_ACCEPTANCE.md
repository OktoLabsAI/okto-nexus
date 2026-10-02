# NS15.05 documentation and identity/cache acceptance

The R4 operations guide, README, active MCP resource descriptions and dashboard
help have been reviewed against the current command and route implementations.
The installed normative documentation test checks seven CLI help commands,
thirteen route declarations, Core adapter IDs, HTTP authentication guidance and
the actual JavaScript referenced by the installed dashboard HTML. The dashboard
is rebuilt from reviewed frontend source into the isolated wheel, preserving
preexisting worktree static assets. This is unit-contract acceptance, not browser
usability or full provider execution acceptance.

The README no longer advertises the obsolete surface revision, table/tool counts,
or dual-transport parity. Its old token measurement is explicitly historical.
Legacy administration notes identify the current identity resource revision.

## Scenario crosswalk

| Scenario | Evidence and causal scope |
|---|---|
| TR4-15-05 | `test_ns15.py::test_ns15_05` exercises installed CLI help, compares documented routes with installed declarations, verifies no retired stdio startup instruction in installed help/assets, and checks qualification/unknown-outcome limitations. Manual review corrected README surface/schema claims and marked retained legacy references. |
| TN-38 | `test_ns03.py::test_ns03_01` authenticates one Agent through public `/v1/connections/me` among 100,000 others, checks indexed lookup, scoped response and spoof denial. `test_auth_cache_bounds.py::test_100k_sqlite_identities_use_indexed_lookup_and_bounded_cache` resolves all 100,000 keys through SQLite with indexed lookups, bounded memory and unchanged thread count. No provider is used. |
| TN-39 | The same 100,000-key workload checks memory plateau at 4,096 entries, churn, expiry and synchronous revocation/reactivation. The invalidation race cases prevent a stale lookup repopulating the cache. `test_ns03_01` verifies old-key refusal and credential epoch increment after rotation through the public API. |

Installed campaigns use `-I` outside the checkout. Every installed package file
is compared with its wheel, and nonstatic Nexus source bytes are compared with
the checkout. The runner records the three artifact hashes, command lines and
test source hashes. Counts are distinct current nodes, not totals accumulated
across repeated runs. See `test_runs_20261001_ns15_05.json`.

## Remaining acceptance

The original TN-40 evidence gap was subsequently addressed by the
[supported recovery campaign](M12_TN40_ROLLBACK.md): three installed checks passed
after backfill and a synthetic uncertain native effect, preserving policies and
history. It proves same-version snapshot recovery, not reverse SQL migration or
old-binary compatibility. [Scenario reconciliation](M12_NS15_05_MCP_RECONCILIATION.md)
records the exact historical artifacts for all four NS15.05 scenarios.
Task dependencies and G0–G3
remain open. This campaign uses Windows/Python 3.13 and does not establish the
final platform/provider matrix, independently hosted remote execution, browser
interaction, CI or release artifact acceptance.

The final M13 build must use the committed documentation and rebuilt frontend.
This intermediate wheel was built before the README count corrections in this
increment; README metadata is not represented as final release documentation.
