# Installed regression shards 2 and 3

This is a failed/incomplete fullsuite campaign, not a release PASS. The immutable wheel under test is Nexus 0.3.6, SHA256 `01eb1ce064f62b09630c24b5ad339814b9e46c429a7c4e7ebf7561eae23cfff6`.

Shard 3 completed naturally: **1821 passed, 36 failed, 54 skipped**, 17 warnings, 5271.40 seconds, exit 1. Its XML, campaign, effective command, installed preflight and parent import-origin reports are copied here. All three parent application families resolve to the frozen installed prefix; no bad origin was reported. Input comparison reports no changed inputs. The final process observation found no recorded CI child or process bearing this campaign's temporary-root marker; observer ancestors were excluded.

Shard 2's original run produced 145 passing and 3 failing call reports, then stalled in TestClient shutdown after a failed call. Its call trace was not captured, so those three causes remain unknown. The authorized containment verified the exact owned process identity before stopping that pytest process; all four recorded campaign processes were subsequently absent. Three derivative waves each captured another failing native-approval handshake and stalled in teardown. Their traces show runtime.open reconciling/outcome unknown, not a proved provider action. They were contained with their dedicated process group. The orchestrator was stopped between waves, with zero children; **2031 collected nodes remain NOT_RUN**. No derivative passing result is claimed. See the original interruption, stopped summary, boundary stop and retained raw paths.

## Failure interpretation

`shard3-failures.json` preserves all 36 literal traces, with conservative classifications:

- Thirteen migration tests have stale migration-list expectations: eleven expect only 162/163 and two stop at 160, while the current runner also applies later migrations through 168. They stop before their semantic row/preference assertions. A future test-only change should update the expected migration range while retaining those semantic checks; no change was applied here.
- The first legacy multi-harness test expects the former `Resume codex` / `a. Add another connection` menu; actual output offers the public-ID conflict choices `r/i/s/c`. The second feeds `['a', 'y']` into the current review protocol. The implementation accepts only `y` to call flow.apply (connect.py 504–527), so `a` returns 0 before the expected simulated Finish failure. This is an incompatible scripted input, not proof that the later recovery assertions pass. Update the script to the explicit current menu/review intent in a separate reviewed test change.
- Three renewal-cost cases call an instance method with `self=None` and fail on `_lease_wake`. Six remote-preparation cases include a Connector fixture child AttributeError for missing `service_generation`; another process-death case reports an exited Connector child. Two Connector binding-approval cases attempt unprovided interactive stdin under pytest capture.
- Recovery, lease scheduling, shutdown timeouts, managed MCP action-set mismatch and the remaining failures are retained as unresolved observed failures. This report does not attribute them to a historical baseline without a comparative run.

## Scope and reproduction

The drivers invoke the existing immutable `tools/ci_installed.py test --tests tests --shard-count 4 --shard-index 2|3 --wheel <frozen wheel> --output <own Temp>` with sanitized environment and own temporary homes. `run_shard.py` preserves isolated Python, temporary working directory and pytest configuration without checkout pythonpath, adding an installed parent-origin guard. Some unchanged regression tests intentionally launch children with source PYTHONPATH: `provenance-boundaries.json` records this static boundary. Parent installed origin is therefore **not** an all-child installed claim.

No provider/native harness campaign, personal authentication, Windows session event, package installation or product/test/CI modification was performed. Fake peers and synthetic records are regression fixtures. `finalize_report.py` only reads/copies existing evidence and observes owned process absence; it does not execute pytest. No tests were started after shard 3 completed. Raw stdout remains at the hashed external path in `manifest-final.json`; temporary data were preserved.

Curator commands: `rtk proxy python -B NEXUS_QUICK_CONNECT_R1/execution/qc09-installed-23/finalize_report.py` (exit 0). Results and byte pins are in `qualification.json` and `manifest-final.json`.
