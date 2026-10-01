# M08: operational native proposals and Claude MCP permission channel

Date: September 30, 2026. Core increment published at 6cf2ecc, version 0.2.41.dev0. M08 remains incomplete.

The real Codex/Claude journeys exposed native permission refusals. Core now keeps the immutable operational request separate from its redacted display, as required by the R4 HTTP/NXL contract. Only the adapter correlation port may supply that proposal; an arbitrary native event payload cannot create pending approval authority. The original typed ID, hash, parameters and generation survive unchanged. The emitted category distinguishes approval and input, with the originating operation ID.

Claude now recognizes bounded MCP tool names as requests requiring an explicit decision. The original input is retained for the native reply; wrong-tool correlation and duplicate application are refused. Adding the approved model/MCP arguments to the standard stream command no longer disables the stdio permission channel. This is not automatic tool permission.

The normalized wheel and sdist passed clean package/import/resource and embedded/remote smoke verification. A separate environment containing Core and test dependencies, with both application packages absent, passed 54 tests. The runner checked source/wheel/installed byte equality and artifact hash. Pip check passed. These are technical adapter tests, not new real-provider acceptance.

## Transactional request ingress and consumer adoption

Nexus 49b2422 and Connector ab6bfaf adopt the same Core 0.2.41 wheel. Nexus migration 087 adds captured native requests without inventing a deciding actor; confirmed decisions continue to belong to execution_decisions. Event ingress materializes only the contiguous prefix, inside the ACK transaction. Authority comes from the admitted turn, while the original typed native ID, request, hash and generation remain intact. Presentation data is stored separately after redaction.

Duplicate delivery cannot change expiry, display or state. Reusing the same namespaced ID with changed content or another source operation is refused atomically. Numeric and text IDs remain distinct; different stream namespaces cannot collide. Terminal turns and old owner generations produce non-actionable records. Requests delayed behind gaps use their original receipt time for the 120-second application expiry. These persisted facts do not approve tools or apply decisions.

Installed verification passed 55 Nexus cases, the same 55 cases in an environment without Connector, and 45 Connector cases. Both environments passed pip check. The runner verifies source/wheel/installed bytes and artifact hashes. The first installed campaigns exposed a missed Nexus inventory version constant; their 55 setup errors per environment and the single-case diagnosis are preserved. After correction, the Nexus wheel was rebuilt and both complete campaigns passed. Preexisting UI assets are excluded from UI acceptance and commits.

Evidence: [consumer test index](test_runs_20260930_native_requests.json), [consumer runner](run_native_request_installed.py), and evidence/native-request-*. The 35-case source run predates the final five native classification/namespace cases; installed results cover all 55 selected cases.

Next work remains the existing M08 scope: authenticated operator CAS, one decision/input outbox operation, native capture/application in both hosts, explicit sensitive-input retention, then real-provider replay and failure tests. The actual Codex MCP permission request still needs observation before choosing its translation.

Evidence: [working checkpoint](m08_native_approval_working_checkpoint.json), [installed runner](run_native_approval_core_installed.py), and evidence/native-approvals-core-*. No milestone or release gate closes.
