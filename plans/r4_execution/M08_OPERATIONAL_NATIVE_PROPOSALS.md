# M08: operational native proposals and Claude MCP permission channel

Date: September 30, 2026. Core increment published at 6cf2ecc, version 0.2.41.dev0. M08 remains incomplete.

The real Codex/Claude journeys exposed native permission refusals. Core now keeps the immutable operational request separate from its redacted display, as required by the R4 HTTP/NXL contract. Only the adapter correlation port may supply that proposal; an arbitrary native event payload cannot create pending approval authority. The original typed ID, hash, parameters and generation survive unchanged. The emitted category distinguishes approval and input, with the originating operation ID.

Claude now recognizes bounded MCP tool names as requests requiring an explicit decision. The original input is retained for the native reply; wrong-tool correlation and duplicate application are refused. Adding the approved model/MCP arguments to the standard stream command no longer disables the stdio permission channel. This is not automatic tool permission.

The normalized wheel and sdist passed clean package/import/resource and embedded/remote smoke verification. A separate environment containing Core and test dependencies, with both application packages absent, passed 54 tests. The runner checked source/wheel/installed byte equality and artifact hash. Pip check passed. These are technical adapter tests, not new real-provider acceptance.

Nexus and Connector remain pinned to published Core 0.2.40 until the adoption increment verifies their handling of operational versus display data. Next work remains the existing M08 scope: canonical request persistence, operator CAS, one decision/input outbox operation, native capture/application in both hosts, explicit sensitive-input retention, then real-provider replay and failure tests. The actual Codex MCP permission request still needs observation before choosing its translation.

Evidence: [working checkpoint](m08_native_approval_working_checkpoint.json), [installed runner](run_native_approval_core_installed.py), and evidence/native-approvals-core-*. No milestone or release gate closes.
