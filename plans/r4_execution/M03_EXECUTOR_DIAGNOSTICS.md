# Scoped executor recovery guidance

Nexus 6184739 projects actionable US English guidance for existing provider-authentication, required-authentication-material, missing-binary, unqualified-build, rediscovery and profile-drift receipt codes.

The public operation error names the canonical executor and binding. It preserves receipt code, possible_effect, retry_safe and operation ID. A possible native effect always puts operation/session reconciliation before new work. Unknown errors receive generic inspection guidance. No raw native error text, local path or credential is needed by the projection, and reading an operation produces no new execution.

Installed verification passed 21 Nexus tests and 60 Connector consumer tests. Fourteen API cases exercise seven codes with and without possible effect, authenticated receipt persistence, ErrorBody schema, foreign-agent refusal, credential exclusion and unchanged operation/receipt counts. Receipt history, session metadata and a public runtime CLI journey also passed. The earlier source run passed 15 overlapping cases.

See [manifest](test_runs_20261001_executor_diagnostics.json) for wheel hashes, commands and evidence. Core and Connector remain unchanged. There is no migration. Native missing-login detection and the remaining NS05.05 acceptance still require their own evidence; this increment does not close that requirement or any release gate.
