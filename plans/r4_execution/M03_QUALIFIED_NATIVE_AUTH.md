# Qualified native authentication diagnostics

Core 3982f6b / 0.2.46.dev0; Connector 96d11cf; Nexus 581df44.

## Delivered behavior

Codex terminal HTTP 401 variants now preserve PROVIDER_AUTH_REQUIRED. HTTP 403 and unknown variants remain generic native failures. Pi's correlated negative prompt response is persisted as FAILED; its qualified missing-key preflight format identifies PROVIDER_AUTH_REQUIRED. A transport-loss response without a native request ID remains OUTCOME_UNKNOWN.

Receipts preserve possible_effect=true and retry_safe=false. Replaying the operation returns the stored receipt without a second native send. Diagnostic classification never uses ordinary model output.

## Installed verification

- Core: 72 passed in 101.70 seconds, including real Pi, Codex and Claude missing-login cases.
- Connector: 122 passed in 41.36 seconds.
- Nexus: 21 passed in 72.27 seconds; one dependency deprecation warning.
- Source, wheel and installed module bytes were compared before testing. pip check and uv lock --check passed.
- Core SHA-256 in all three repositories: 302431373fc9a4d540b6865dee5aedcff50de7694d8d730963dbb503bd3dd1b8.

The native tests use empty temporary provider homes, the normal Core factory and unchanged native qualification. Existing login files were not changed. The [manifest](test_runs_20261001_native_auth.json) preserves failed attempts and artifact hashes.

## Remaining acceptance

Public consumer missing-login journeys, the final positive campaigns for this artifact set, Linux, independent hosts and UI remain pending. NS05.05 and G0–G3 remain open. This increment advances M03/M07 without declaring their full acceptance.
