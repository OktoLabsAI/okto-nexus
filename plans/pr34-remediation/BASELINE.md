# P00 baseline — 2026-09-22

Runtime source: PR34 `d7d87d0c3ee2ea2ed7c63cdb8f9cafdbd5ee0397`;
merge-base `27b06fe48b9f95b35c94f50827fea83d178f4e12`.
Version-only milestone `8307965` changes package/docs to 0.2.0, not runtime.
Windows, Python/environment and exact MCP schemas captured in
`evidence/p00-contracts.json` (51 tools, surface revision 34, migrations 001–029).
All stores were temporary; no personal runtime was opened.

## Commands and observed results

| Command | Observed result | Evidence |
|---|---|---|
| `.venv/Scripts/python.exe -m pytest --collect-only -q` | FAIL: 1830 collected and one collection error, `os.geteuid` unavailable on Windows | p00-collection.log |
| `.venv/Scripts/python.exe -m pytest -q --ignore=tests/test_claude_code_attach_connector.py` | FAIL: 1814 passed, 13 failed, 4 skipped, 337.87s | p00-baseline.log |
| `.venv/Scripts/python.exe -m pytest tests/test_pr34_remediation.py -q` | 20 behavioral failures, 21.47s; expected red baseline | p00-red.log |
| `uv lock --check --offline` | PASS after version bump | version milestone 8307965 |
| `codex --version` | codex-cli 0.155.1 | observed shell output |
| `claude --version` | Claude Code 2.1.277 | observed shell output |

The regression fixture uses the actual production FastAPI composition, middleware,
MCP mount and SQLite against a real TCP socket. Only the external connector is a
synthetic peer. The auth failures are successful unauthorized tool responses,
not import errors or authentication setup failures. The collection error above
is recorded separately and never counted as a security reproduction.

Existing failures include six Claude protocol/portability tests, one Codex
handshake test and six POSIX-oriented shutdown/watchdog tests. Logs preserve
the exact failures; they are not newly caused by remediation. Four baseline
skips are pytest skips, not accepted NOT_APPLICABLE gates in the new matrix.

## Native test authority

User approved installed Codex and Claude for isolated real testing. No native
model call has yet run in this campaign. Pi is NOT_RUN by user decision.
Claude attach requires a dedicated test session, never discovery/reuse of a
personal session. Preserve sandbox/approvals; do not pass Nexus operator keys.

## Retained local files

Generated dashboard changes and `.nexus-policy-guardrail-test/` predate this
work and are excluded from remediation commits. Six supplied root documents
are the authoritative specification. No database migration/backup of the
user's real store has been performed. No destructive rollback is permitted.
