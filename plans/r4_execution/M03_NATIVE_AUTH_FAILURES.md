# Native authentication failure receipts

Core 3823ae3 / 0.2.45.dev0; Connector e67eb87; Nexus 12e2c41.

## Behavior

The copied adapter bridge recognizes Claude's structured authentication_failed API-error marker and Codex's unauthorized CodexErrorInfo. Classification is associated only with the active operation and, for Codex, its active native turn. Ordinary output text and payload-injected diagnostic fields do not establish authentication failure.

Claude result errors now follow the correlated terminal-turn path. The journal atomically concludes the existing operation as FAILED and persists PROVIDER_AUTH_REQUIRED when the bridge observed that structured fact; other terminal failures use NATIVE_OPERATION_FAILED. Native effect and retry facts remain conservative: possible_effect=true, retry_safe=false. Success and interruption do not inherit an earlier authentication error. No new operation or native retry is created.

## Installed verification

- Core: 58 regression cases passed; the corrected real Claude missing-login case passed separately on the same wheel in 11.05 seconds.
- Real Claude used an empty temporary provider home, the normal LocalRuntimeCore and CopiedAdapterFactory, and unchanged native build qualification. Existing user login files were not modified.
- Connector: 122 cases passed using that Core wheel.
- Nexus: 21 API, receipt, session-view and public HTTP/WSS journey cases passed after updating its inventory version constant.
- The same Core wheel hash is present in all three repositories. Nexus uv.lock was updated through local wheel resolution.

The manifest retains the initial fixture errors, four product reproductions and the obsolete Nexus version-pin failure. See [commands, hashes and results](test_runs_20261001_native_failures.json).

## Remaining acceptance

Real missing-login campaigns for Codex and Pi, Pi-specific classification, and the complete missing-login journey through public Nexus/Connector entries remain pending. The prior positive real-provider campaigns are historical evidence for their recorded wheels; they are not relabeled as campaigns for Core 0.2.45. NS05.05 and release gates remain open.
