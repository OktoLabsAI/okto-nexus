# P12 — complete Windows regression inventory at feeb14d

Implementation/test SHA: `feeb14d171d9dad4bc7ee5400c6bb10db8a6ec53`.
No implementation or test changed until the run ended. Documentation-only audit
commit bdb1ca6 landed while it ran. This is not the final acceptance gate.

Command: `rtk proxy .venv/Scripts/python.exe -m pytest -q --tb=short --basetemp=<unique-temporary-tests> --junitxml=<temporary-results.xml>`.
The wrapper removed native campaign/test configuration flags and set legacy live
flags to zero, then wrote `evidence/p12-suite-feeb14d.json`. Raw XML stays in the
unique `okto-full-suite-feeb14d-*` temporary directory; credentials/logs were not
copied into repository evidence. Exec session15489 is terminal; do not restart it.

Observed: **2296 PASS, 4 FAIL, 117 SKIP, 2 warnings in1686.22s**. The warnings were
the existing Starlette/httpx deprecation and injected Pi death-callback exception.
The117 skips retain their unexecuted/platform/opt-in meaning, not blanket PASS.

## Failures and corrections

Three `test_failed_interrupted_and_unknown_results_do_not_relay` variants opened
an initial successful Codex fixture connection, then replaced its factory with a
different outcome. Production multiplexing correctly reused the already opened
compatible connection; its actual successful output relayed once before the second
agent's failed fixture output. The fixture now configures the desired outcome
before its first open via `codex_session(outcome=...)`. Assertions still require
one result/one operation and no relay for failed/interrupted/unknown terminals.

`test_terminal_is_correlated_to_transport_attempt_and_releases_lane[False-True]`
set a failure event inside a rolled-back projection, but allowed the next automatic
retry to commit before asserting that delivery was unread. The test now keeps the
injected terminal projection failing until it checks the rollback snapshot, then
explicitly releases recovery. No sleep increase, production retry suppression or
weaker assertion was introduced.

`rtk proxy .venv/Scripts/python.exe -m pytest -q --tb=short tests/test_runtime_relay.py tests/test_runtime_result_correlation.py tests/test_runtime_commands.py`:
**39 PASS in138.43s**. Ruff on changed fixtures PASS. This selected rerun does not
convert the prior complete run into a full PASS or substitute for the final matrix.

## Next dependencies

The independently reproduced store writer-mode defect is being corrected in
`../okto_nexus_writer_fence_worktree`, detached at bdb1ca6, with its own test venv.
No commits are made there; integration/commits belong to feature/v0.2.0. Migration057,
transactional compatibility/mode fences and tests are uncommitted there. Combined
backup/restore, broad effective capabilities and remaining P12 gates remain pending.
