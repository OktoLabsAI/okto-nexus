# PR-03 — optional preset evolution

Date: 2026-11-05. Windows 11 10.0.26300, Python 3.13.1. Scope: DX-21 and
DX-T51, with narrower reconnect/receipt subchecks in DX-T41/46 and INV-26.
Nexus 0.3.3 / `feature/v0.3.3`; Connector 0.0.12 and Core 0.0.14 unchanged.
Fetched all three `origin/main` references again; each is contained in its
working branch. The fixed R3 plan is unchanged.

## Behavior

`okto-nexus preset` explicitly reviews adoption or evolution of the saved
project connection. The Server compares current values, recorded old defaults
and current recommendations. Only unchanged old defaults advance; individual
customized harness settings and other personalized values remain. Revision-1
legacy receipts have an immutable known base; an unknown base/newer stored
revision is refused. The shipped recommendation remains revision 1. Future
revisions 2/3 are injected in tests, not released by this milestone.

The review is readonly on both HTTP adapters and operator-only. Its revision
covers canonical configuration, identity, selected binding, current authority,
defaults and all affected execution authority. Runtime/session policy changes
can revoke grants and disable boot approvals across every connection of the
identity; the review lists those effects and guards concurrent changes on other
connections. Only the selected active connection receives the reviewed new
grant. Disabled runtime remains disabled without a model test or new grant.

Application reuses ordinary Test/Finish, authorization, baseline checks and the
existing atomic setup receipt. No new table, generic template infrastructure or
authority model was added. Identity/name/role/coordination permissions, MCP,
host paths, credentials, execution-location preference and Server policy stay
intact. Unreviewed path, auto-claim and MCP modifications are refused before
Test. Late receipt failure rolls back configuration and authority together.

Local active updates explicitly disclose version checking and the model test.
Existing remote Connector bindings use human operator authority and Server
Finish without local service fallback, remote probes/tests or productive work.
The original project association/request/result remains intact; the existing
profile retains a separate update checkpoint. Lost Test/Finish responses recover
the same request. Confirmed refusals and failed tests with confirmed cleanup
allow a new explicit review; uncertain operations cannot be discarded by
`--refresh`. Old committed Finish requests still recover/replay after revision
advancement. Ordinary reconnect never applies the new recommendation.

## Validation

JUnit reports retain the development sequence; overlapping runs are not added
as distinct coverage:

| Report | Result | Scope |
| --- | --- | --- |
| `pr03-preset-evolution-source.xml` | 33 passed, 1 failed | Initial Server/connect/identity regression; unknown future origin returned the wrong error category. Corrected to existing VALIDATION_ERROR contract. |
| `pr03-preset-evolution-terminal-source.xml` | 7 passed | Early merge/terminal recovery cases. |
| `pr03-preset-evolution-boundaries-source.xml` | 7 passed | Legacy base, late rollback, tampering and corrected origin validation. |
| `pr03-preset-evolution-final-source.xml` | 20 passed | Canonical review, concurrency, all-binding revocations, local/remote CLI and recovery at that development point. |
| `pr03-preset-evolution-installed.xml` | **148 passed, 8 skipped** | Final wheel; new preset suites plus setup/recovery/Test, connect/identity/policy, remote policy/operator, diagnostics and terminal HTTP regression. |
| `pr03-preset-evolution-cleanup-installed.xml` | 4 passed | Additional assertions after actual asynchronous cleanup; overlaps the broad suite. |
| `pr03-preset-evolution-reconnect-installed.xml` | 3 passed | Additional assertions for ordinary reconnect after a preset revision change and replay of old committed Finish; overlaps the broad suite. |

The eight skips are all existing `test_connection_workflow_dashboard.py` browser
cases with reason `Browser campaign disabled` (`OKTO_NEXUS_UI_CAMPAIGN` unset).
No new browser acceptance is claimed. The broad run emitted the existing
Starlette TestClient/httpx deprecation warning. Earlier focused development
also exposed Core authorization normalization differences; normalization was
corrected before the installed artifact was built. The final lint pass fixed
only an imported pytest fixture alias in `test_connection_test.py`; production
bytes did not change after the wheel build.

Five actual installed CLI cases passed: help, absent profile with/without
`--plan`, conflicting approval flags and NaN timeout. All preserved absent home
state. `pr03-preset-evolution-cli.json` records exit codes and site-packages
provenance for all three packages. Ruff E9/F and staged whitespace checks pass.

Fresh artifact campaign:
`C:\Users\jpamb\AppData\Local\Temp\r3-preset-evolution-evx8hpgi`.
Build used a fresh source copy and `rtk proxy uv build --wheel`; installation
used a fresh venv with all three wheels, Nexus serve-lite and test dependencies.
Tests/schema fixtures were copied outside the checkouts; pytest ran with
`validation/Scripts/python.exe -I -m pytest`, without checkout PYTHONPATH.
The broad suite contains:

```text
tests/test_project_preset_merge.py
tests/execution_r4/test_project_preset_update.py
tests/execution_r4/test_terminal_preset.py
tests/execution_r4/test_connection_setup.py
tests/execution_r4/test_connection_setup_recovery.py
tests/execution_r4/test_connection_test.py
tests/execution_r4/test_connection_workflow_dashboard.py
tests/execution_r4/test_terminal_connect.py
tests/execution_r4/test_terminal_identity.py
tests/execution_r4/test_terminal_policy.py
tests/execution_r4/test_remote_project_policy.py
tests/execution_r4/test_remote_operator_terminal.py
tests/execution_r4/test_project_diagnostics.py
tests/test_terminal_http.py
```

The manifest `pr03-preset-evolution-wheels.json` records exact source byte/set
comparisons: Nexus **436 Python files + 7 static assets**, Connector **117**,
Core **130**. Nexus SHA-256:
`de68e8d53452fc8721e45c2a95798cc8ce5e1eadab3307513454c7b92199d470`.
Connector/Core pins and payloads are unchanged. No release or package upload.

## Limits

HTTP authorization, canonical handlers, SQLite transactions, setup receipts,
policy/grant invalidation and the real Connector onboarding service are used.
Inventory, version checks, native harness/model turns and HTTP transport bridges
are synthetic; the remote operator vault is in memory. The five console cases
run actual executables and intentionally require no provider or credentials.
Real two-host execution, OS vault/TLS, productive M1, participant configuration,
coordination smoke and native login/service qualification remain open. No
personal service was registered, no paid inference or real credential was used.
DX-21/PR-03 and full R3 remain in progress; this evidence qualifies the declared
optional-evolution contract, not complete productive acceptance.
