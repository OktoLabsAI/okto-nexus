# Local real harness campaign — September 30, 2026

User-authorized Windows tests used installed Core 0.2.30.dev0 and the existing local provider authentication. The commands and metadata are preserved in [the manifest](evidence/local-harness-campaign-manifest.json). Application repositories were not used as provider workspaces.

## Native adapter results

| Harness | Observed build | Observed results |
|---|---|---|
| Pi | 0.87.1 | Queued steer, terminal settlement, abort, successful follow-up, bounded shutdown with observed process stop |
| Codex | 0.159.0 | App-server handshake, completed turn, completed steered turn, interrupted turn, connector close |
| Claude | 2.1.282 | Two successful stream turns, interruption while generating, terminal result, observed process stop |

All three native probe commands exited successfully. Result fields were checked explicitly: process exit alone is not acceptance. The interrupted Claude result is `error_during_execution`; the two ordinary turns reported `success`.

## Production factory

The installed Core factory is tested separately without qualification overrides. Codex 0.159.0 is refused with `NATIVE_VERSION_UNQUALIFIED`. This newer build requires an exact qualification update and installed regression evidence before normal launches can succeed.

Claude opens and submits, correlates its terminal event to the operation, and records `SUCCEEDED`. Close initially reports `OUTCOME_UNKNOWN`; the subsequent shutdown reports `already_closed`. This is preserved as an unresolved close observation.

Pi opens and submits through the production factory, records a correlated successful terminal and `SUCCEEDED` receipt, accepts close, and reports `already_closed` on shutdown. Evidence: `evidence/local-managed-pi_rpc.json`.

## Limits and next required work

These probes exercise the real adapter protocols and the legacy public Core runtime context. They do not close R4 embedded/remote product acceptance. The next acceptance work remains the existing plan: qualify the installed Codex build, exercise R4 authority and leases, test direct Nexus and Connector public journeys with approved tool configuration, and resolve observed failures.

Existing provider homes may load user settings and registered MCP servers; these probes do not prove isolated approved MCP configuration. Credentials and model output are not included in reports. Two Pi timing flags have insufficient instrumentation and are excluded from acceptance conclusions, as recorded in the manifest. Linux and independent remote hosts remain pending. No milestone or release gate is closed.
