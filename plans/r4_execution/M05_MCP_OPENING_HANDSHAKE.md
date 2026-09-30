# Selected version observation and opening MCP handshake

Date: September 30, 2026. Partial M05/M06/M09; M08 remains required. No milestone or release gate closes.

## Changes

Core 0.2.40.dev0 observes the version of a selected executable when passive discovery left it unknown. This happens at the admitted launch boundary, with containment, fingerprint checks and lease/content guards before the version process and after its result. It resolves no provider credentials and preserves the prepared identity. The existing exact-build qualification is still required. Core is published at ae9be53; Connector adopts the same wheel at 67f2ea0.

Native MCP clients initialize during runtime.open, before the receipt marks the session READY. Nexus now accepts only initialize, notifications/initialized, tools/list and ping in OPEN_PENDING under the current applied lease and unchanged capability/grant/scope. Tool calls, resources and prompts still require READY, and domain transactions reauthorize independently. Revocation continues to invalidate transport authentication.

## Installed verification

- Core: 101 passed, including missing-version qualification and expiry/content guards.
- Connector: 45 passed with Core 0.2.40.
- Nexus: 79 passed on the final opening-handshake wheel.
- No-Connector environment: 78 overlapping cases passed; the one case importing the Connector application was deselected.
- Clean Core wheel/resource/consumer checks and pip check passed.

The Core installed runner initially failed to import a tests-only helper. Adding the repository root using forward slashes fixed Windows argument parsing; no src directory was added. Both collection failures are retained.

## Real provider results and next fixed-plan work

Codex 0.159.0 initially refused open because the passive candidate lacked a version. After the Core fix it opened, renewed its lease and completed a turn, but its MCP initialization received 401. After the Nexus fix the session MCP reached ready. The provider then attempted handoff_get, which the native permission path rejected. The handoff remained OPEN, so the journey correctly failed.

Claude 2.1.282 opened, renewed, connected to the session MCP and completed a turn. Its native permission path denied handoff_get; the handoff remained OPEN. During failed-test cleanup, an open MCP HTTP stream prevented the test server from entering lifespan shutdown. The test process was stopped after identity verification and its protected test credential was removed after process-stop confirmation. The harness now bounds HTTP drain before owner shutdown.

These results identify the next work already required by M08: compose native approval/input capture, public decisions and unique native application in embedded and remote execution. Neither native permission policy nor build qualification was bypassed. Rerun both real journeys after that integration. Previous Pi success remains evidence for its earlier artifact set.

Evidence: [coordinated manifest](test_runs_20260930_mcp_opening.json), [real runner](run_real_embedded_mcp.py), [opening regression runner](run_mcp_opening_installed.py), [Core regression runner](run_launch_observation_installed.py). Failed attempts and sanitized diagnoses are retained under evidence/real-embedded-mcp-*. Nexus UI bytes remain outside this commit and acceptance.
