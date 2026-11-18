# Canonical J5 / J7 assembly (prepared, not executed)

J5 no longer needs a forged row or an operator agent key. `canonical_controls.py` defines these steps:

1. Canonically register two own subjects and issue their own keys. TerminalConnection Review/Test/Finish creates the worker binding and reviewed execution policy. Check actual endpoint consumption is exclusive; migration/default is exclusive, but refuse if it differs instead of SQL patching it.
2. Creator's authenticated MCP `handoff_create` supplies acceptance criteria and `verify_by={kind:agent,agent_id:operator}`. Creator is **not** worker or verifier. MCP uses an actual subject key and an empty Cookie header to avoid mixing human and agent identities.
3. Operator explicitly issues one `execute_work` grant for the own worker/endpoint with original600s window. Claim through worker MCP with endpoint/grant/idempotency ID. This is managed work, not a manually assigned operation ID. Keep the returned runtime operation/domain delivery IDs.
4. Full inert peer emits canonical events. After actual terminal receipt, read `handoff_get`: status must still be CLAIMED. That proves turn completion did not complete task. Then worker MCP `handoff_complete` must produce VERIFYING. Do not bypass execution-tool or claim fences; if refused, record the exact gap.
5. Browser reads Results before verification. Then actual operator session REST `POST /api/v1/workspaces/W/handoffs/H/verify` records verdict under domain anti-self-verification/eligibility. Read Results again: same result ID/claim, new semantic revision and exact verification evidence. No arbitrary event insertion. Browser is observer, not verifier, in this lane.

This uses real product use cases and HTTP auth. It is synthetic work/output, not real model QA. The code is only prepared; current installed package behavior must be measured after READY. `test_canonical_handoff.prepare` is **not** reused because it edits endpoint SQL. `test_verification.make_env` is **not** reused because it creates capability/policy rows directly. Nothing here patches recipient/claim/grant/receipt/frame.

J7 actual reader-auth revocation:

1. New operator account via canonical account API inside own home, password generated in memory. Canonical login creates own human session. No personal account or agent key representing operator.
2. Write its cookie only to private Temp Playwright storage; never curate it. `BrowserSurface` enforces the product's `X-Nexus-Operator-Session-Required:1` header for all browser API requests, closing local-open fallback.
3. Seed/finalize admissions before browser baseline. Load exact viewer with valid cookie and then POST logout through the actual product endpoint from host control. Old cookie is revoked; subsequent browser API must return401/403 and clear protected content, even paused. This is real session revocation, not fulfill403 or SQL expiry.
4. A separate grant DELETE tests loss of execution authority only. It must not be called proof of operator read revocation. No implicit reissue/renewal follows.

Partial source lane uses only an own instance read-port fault: `_results` raises sqlite3.OperationalError and the actual source collector marks Results unavailable; other queries remain real. Restore in finally. It does not fake a successful empty result or override JSON. Treat this as partial-source qualification, not network/host outage.

Delayed info lane: hold only the first real `/api/v1/info` response for12s using the ASGI boundary. Do not change payload or client state. Observe whether operational v1 can mount/open a panel before v2 capability arrives. If bootstrap prevents it, report that fact. If a draft exists, verify exact target/text/focus across capability upgrade; never fake a component to force the path. This may expose a real bug and is not yet PASS.

Resource policy: startup/readiness180s; one browser/session; short independent lanes within original authority windows; Core peer finite100s gate; no authority clock manipulation. Canonical close/stop and known birth checks first; forced containment is opt-in for verified own children, never broad process kill. Private DB/cookies remain in Temp. Empty provider environments and immutable installed payload/source pins are checked before/after.
