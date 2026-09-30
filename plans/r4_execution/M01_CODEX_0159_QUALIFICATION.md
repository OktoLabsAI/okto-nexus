# Core 0.2.31 — Codex 0.159.0 and real R4 native tests

The exact installed Windows/x86_64 Codex 0.159.0 executable is now qualified for conversation, steer and interruption. The grant is bound to the observed fingerprint or portable content identity; it does not grant native approvals/input or qualification on other operating systems.

Nexus and Connector pin the same Core 0.2.31.dev0 wheel. SHA-256: `6e3e6e08acee45c8c220bb87d8f79b9697cc95c177b73f37414aa601880d6339`. Nexus also updates its strict inventory version guard. Initial guard failures and final campaign results are retained in the [coordinated manifest](test_runs_20260930_codex_0159.json).

## Real native execution

The installed Core production factory opened Pi 0.87.1, Codex 0.159.0 and Claude 2.1.282 with R4 lease authority installed beforehand. All completed a correlated successful turn and persisted a SUCCEEDED receipt.

Pi accepted close; Codex and Claude reported OUTCOME_UNKNOWN on close, then already_closed on shutdown. A separate active Codex shutdown probe completed within 4.17 seconds and refused subsequent submits, but returned unknown. These outcomes remain open acceptance observations.

The lease grants in these Core probes were constructed locally. The probes do not prove Server-issued authority, the complete embedded/daemon journey, isolated approved MCP configuration, Linux or independent remote hosts.

## Verification and next work

The full installed Core suite passed 951 tests with 74 skips and three warnings. Connector passed 336 tests with one existing skip. Nexus results are in the manifest and XML. Tests cover exact qualification and refusals for drift, platforms and adapters, plus affected installed consumer integration.

Remaining work stays in DELIVERY_PLAN.md: renewal/reconciliation, protected login composition, direct and remote product journeys, event/decision/domain completeness, UI/CLI and US English acceptance, recovery/migration and final provider/OS gates. This increment closes no full milestone or product gate.
