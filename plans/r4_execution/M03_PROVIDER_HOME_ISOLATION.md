# Approved provider home and public authentication failures

Core 016821f / 0.2.47.dev0; Connector 10a123a; Nexus 5d90a85.

## Correction

The real Codex public missing-login test exposed an isolation defect: setting HOME and USERPROFILE alone did not select the empty approved provider home. Its turn succeeded instead of failing authentication.

The Core now supplies CODEX_HOME from the approved home's .codex directory and creates that directory if absent. Existing configuration and credentials are preserved. Directory errors are sanitized; untrusted homes and caller overrides remain rejected. Codex's explicit directory selection and existence requirement are documented in the [upstream implementation](https://raw.githubusercontent.com/openai/codex/main/codex-rs/utils/home-dir/src/lib.rs). The behavioral defect and correction were verified against the installed qualified Windows binary.

## Installed evidence

| Campaign | Result |
|---|---|
| Core directed regression, including real missing-login providers | 89 passed |
| Connector directed regression | 122 passed |
| Nexus directed regression | 21 passed |
| Public Codex missing login | Passed, 159.30 seconds |
| Public Claude missing login | Passed, 168.43 seconds |
| Public Pi missing login, isolated repeat | Passed, 161.18 seconds |
| Authenticated Codex MCP handoff, close, approved rebind, second turn and close | Passed, 345.22 seconds |

The three public missing-login journeys use CLI subprocesses, the real daemon, HTTP/WSS, OS keyring and unchanged native build qualification. They assert PROVIDER_AUTH_REQUIRED, scoped US English recovery guidance, possible_effect=true, retry_safe=false, matching HTTP/CLI errors, stable operation identity on replay and only one admitted turn. Sessions close and campaign credentials are removed.

Source/wheel/installed bytes matched before testing. Core SHA-256 is identical in all three repositories: 5fa9eb1f583daf4fe3c84aa40bf782267243303c0d2b5a562288aa9de35a8a2b. pip check and uv lock --check passed.

See the [manifest with commands, hashes and retained failures](test_runs_20261001_provider_home.json).

## Open acceptance

The concurrent Pi campaign failed control readiness and shutdown deadlines. The isolated pass does not establish the cause; this remains an M11 investigation. Server release readiness is enabled only by the test helper; this is single-host Windows evidence, not independent-host release acceptance.

Embedded-only missing-login recovery, browser flows, complete drift refusal, unrelated live-session continuity, Linux and final frozen-artifact qualification remain pending. NS05.05 and G0–G3 remain open. Existing modified UI assets were not accepted by this campaign.
