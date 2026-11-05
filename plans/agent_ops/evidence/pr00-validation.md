# PR-00 validation

Platform: Windows 11 build 26300 / Python 3.13.1. All commands run under `rtk
proxy`; Python is the repository-local `.venv/Scripts/python.exe`. Core and
Connector test commands run from their own repositories using that interpreter.
No real provider was invoked and no personal service/configuration was changed.

| Command / suite | Result | Evidence |
|---|---|---|
| pytest connection_setup, connection_test, native_decisions, handoff_claim_transaction, handoff_creation_commit_cuts | 64 passed | baseline-paths.xml |
| pytest tests/execution_r4/test_core_inventory.py | 8 passed | baseline-inventory.xml |
| pytest tests/test_messages.py | 50 passed | baseline-messages.xml |
| Core pytest test_config_document, test_config_persistence, test_harness_config | 51 passed | baseline-core-config.xml |
| Connector pytest tests/unit/test_mcp_config.py | 7 passed | baseline-connector-config.xml |
| node --test tests/*.test.mjs | 36 passed | baseline-frontend.xml |
| npm run build | Passed TypeScript and Vite; existing >500kB chunk warning | Packaged static artifacts in this commit |
| python scripts/measure_agent_ops_baseline.py | HTTP liveness 7.811s; canonical DRAINED shutdown | baseline-startup.json |
| python scripts/check_agent_ops_ledger.py | Complete unchanged scope coverage | ledger.json and checker |

Total baseline tests: 216 passed, in addition to the 34 preparation checks.
FastAPI/Starlette emits a TestClient httpx deprecation warning. No lint/test
failure is dismissed as a warning.

Failures found and resolved: wider runtime tests initially rejected Core 0.0.14
because the inventory constant remained 0.0.13 after the package bump. The
constant is aligned and a distribution-pin guard added; the repeated 64 + 8
tests passed. Initial disposable startup timing used immediate process
termination and cleanup raced a Windows handle. The successful timing instead
used the real canonical shutdown API with a memory-only synthetic key in the
disposable home, and waited for process exit. The failed measurement was not
recorded as a passing campaign.

Limits: no full regression, live browser acceptance, clean installed Nexus wheel,
real provider work cycle, service-manager login/logout/reboot, or Herdr campaign.
The first-use baseline can count the existing seven UI stages and demonstrate
the absent complete terminal route; time to useful provider session/result is
still NOT_RUN. BASE-06 remains partially unverified for that measurement. PR-00
delivers the implementation map needed by PR-01, without closing M1 or any later
gate.
