# P11 — runtime diagnostic dashboard

Parent `b002317`, feature/v0.2.0, 2026-09-23. No API/schema change:
schema054/surface42/identity9. Final gate NOT PASSED.

Runtimes is now a dashboard view backed by the existing authenticated binding and
operator outbox projections. It groups connections under canonical Agent identity
and skills, shows health and declared capability verification, distinguishes
persisted readiness from process liveness and explains detached lifecycle without
claiming native termination. Multiple visible ready bindings prompt selection
review; the UI does not duplicate server selection rules or label every multi-
endpoint Agent definitively ambiguous.

Operation cards distinguish commands and conversational delivery, then display
transport state, ACK evidence, reason and exact attempt/owner/session metadata.
Uncertain states explain that timeout/write/acceptance are not completion. Recovery
remains an operator API mutation with snapshot/idempotency/risk validation; the UI
does not add an unsafe retry button. Native approvals navigate to the existing
canonical review/decision screen rather than add another authorization path.

Both reads are bounded and independently handled, allowing admission-OFF outbox
inspection even when binding discovery is denied. Explicit next/first controls
support50-item pages. Refresh clears stale metadata before fetching and suppresses
late responses using a generation guard. It never contacts a native harness.

Files: frontend/src/views/RuntimesView.tsx, App.tsx and api.ts;
tests/test_runtime_diagnostics_dashboard.py; operator/admin references.

## Executed evidence

All browser API requests go to production Nexus on a disposable loopback store.
Only static build assets are intercepted, built in a temporary directory. Edge
uses a fresh profile and chromium_sandbox=true; non-fixture network is blocked.
No repository static assets or personal browser/profile are overwritten.

- `rtk proxy .venv/Scripts/python.exe -c 'import os,pytest; os.environ["OKTO_NEXUS_UI_CAMPAIGN"]="1"; raise SystemExit(pytest.main(["-q","-rP","tests/test_runtime_diagnostics_dashboard.py"]))'`:
  **6 PASS**,44.42s, Edge153.0.4234.48. Cases: actual uncertain transport, detached
  fake attach session, server-rejected AMBIGUOUS_BINDING with two ready runtimes,
  credential downgrade clearing prior operator data, admission-OFF recovery read,
  and navigation to a pending native permission from a Codex protocol peer.
- Same command with `"-k","unknown_operation"` added:
  **1 PASS**,5 deselected,15.24s after adding command/delivery labels and correcting
  screenshot framing. The first screenshot was scrolled/clipped; the replacement
  uses a taller viewport and restores the scroll position before capture.
- `rtk proxy node frontend/node_modules/typescript/bin/tsc --project frontend/tsconfig.json --noEmit`:
  **PASS**, both before and after the final label update.
- `rtk proxy ruff check tests/test_runtime_diagnostics_dashboard.py`: **PASS**.
- [Reviewed screenshot](evidence/p11-runtime-diagnostics.png): complete unknown
  operation and attempt details, canonical connection grouping and no fake success.

T-API-08 diagnostic scenarios are now exercised in an isolated Windows browser,
together with the native approval/input evidence in P11_NATIVE_INPUT_DASHBOARD.md.
Linux browser and real provider/model runs for this unit are NOT_RUN. This does
not qualify native capability probes, managed-handoff recovery or P12 aggregate
acceptance. The ongoing full-suite inventory started before these changes and
cannot be counted as testing this new view.
