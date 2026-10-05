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

## Canonical operator decisions and embedded application

The next Nexus increment adds migration 088, per-request CAS tokens, canonical
approval queue projection in the event ACK transaction, and the public
approval-decisions POST/GET routes. Only an authenticated operator can confirm;
the subject agent key alone is refused. Confirmation persists the decision,
client intent, operation and outbox together. A competing decision loses CAS,
and an identical client intent returns the original operation.

Dispatch revalidates the operator, subject, binding, grant, lease, source turn
and immutable proposal before SENDING. Native controls use the reserved control
path while the original turn waits. They do not consume a second turn budget.
The embedded host enables the supported native channel only under the HITL
configuration and explicit lease actions. It applies the public Core decision
operation with sanitized receipt binding.

Input responses are held only in bounded producer memory (256 entries, 16 KiB
each, with a usable TTL of at most 120 seconds). Expired entries are discarded on producer access or shutdown. The operation stores a reference and digest. At
dispatch, the exact response is reconstructed into the existing inline NXL
payload and checked against the admitted intent hash. Loss before send produces
AUTHORIZED_INPUT_UNAVAILABLE. An explicit matching replay can resupply input
while PENDING/RESERVED; it cannot resend an operation already SENDING. Operation
metadata is available to its authenticated deciding actor without exposing raw
input. A confirmed canonical decision remains confirmed after a native refusal.

Installed technical verification passed 83 cases in the normal environment and
the same 83 overlapping cases without Connector installed. Source/wheel/installed
bytes and artifact hashes were checked before each run. The final artifact and
results are indexed in test_runs_20260930_native_decisions.json. Source failures, the initial installed
artifact, and the final batch interrupted by Windows modern standby are retained.
Kernel-Power events 506/507 document approximately 834 seconds of standby during
that batch; tickets and leases expired. The real runner now archives a previous
successful journey report before starting, so a failed attempt cannot inherit it.

Remaining M08 acceptance: native capture in the remote host under its applied
lease; actual Codex permission/input mapping; real negative/input/recovery paths;
explicit provider observation for APPLIED_OBSERVED; UI/CLI decisions and their
races; migration and full restart qualification. SUCCEEDED receipt metadata is
currently shown as SUBMITTED, without claiming explicit provider observation.
M08 and all release gates remain open.

### Final installed and real results for Nexus dfa48d5

The Claude journey passed in 88.06 seconds on the final Nexus wheel: three
explicit operator decisions, lease serial 2 before the turn, handoff COMPLETED,
turn and close SUCCEEDED, one tool claim, no WSS tickets and protected credential
cleanup. The native build qualification was not overridden; the Server release
gate was test-only overridden.

The Codex journey failed after 96.08 seconds: its turn completed but handoff_get
was rejected with user rejected MCP tool call. No canonical native request or
tool claim was captured, and the handoff remained OPEN. Selected event metadata
is retained in evidence/real-native-decision-codex-observed-refusal.json. This is
a concrete remaining permission translation defect, not successful domain work.
Core and Connector packages are unchanged in this Nexus increment.

## Observed Codex empty elicitation form - Core 0.2.42

The opt-in observer recorded the real Codex 0.159 request without changing the
adapter's handler result. MCP permission arrives as mcpServer/elicitation/request,
mode form, with an empty object properties map and codex_approval_kind=mcp_tool_call
metadata. The old validator required at least one field. The diagnostic trace is
evidence/real-native-decision-diagnostic-codex-requests.json.

Core c7aa63d / 0.2.42.dev0 accepts that valid empty form under the existing native
input contract. Approval requires the explicit response content={}; denial remains
action=decline. The response never copies the advertised session/always persistence
metadata. Missing responses, added answer fields, persistence instructions and
unsupported schemas remain refused. The real consumer test approves only its three
named governed tools, exact server/workspace/subject/handoff and empty schema.

Source verification passed 57 cases after correcting a source-path collection
mistake. Installed Core verification passed 75 cases with both application packages
absent. Normalized wheel/sdist import, contract resource and local/remote consumer
smokes passed, with pip check. The initial verifier command used an unsupported
positional argument; its log is retained alongside the successful corrected call.
Consumer and real-provider results are recorded in the subsequent test index.

### Consumer adoption and three real local providers

Nexus 75f1af5 and Connector a308cf6 adopt Core c7aa63d with the same 0.2.42 wheel.
Installed regressions passed 83 Nexus cases, the same 83 cases without Connector,
and 45 Connector cases. Pip checks passed. Source/wheel/installed bytes and package
hashes were verified before the campaigns.

All three positive local journeys passed on this same installed Nexus/Core pair:
Codex in 104.86 seconds, Claude in 95.33 seconds and Pi in 360.83 seconds. Each
completed its handoff, succeeded the turn and close, renewed to lease serial 2
before the turn, and removed its temporary credential. Codex and Claude each
received three explicit operator decisions; Pi used three governed native actions.
No Connector application or WSS tickets were used. Native build qualification
remained active; the Server release gate remained test-only overridden.

See test_runs_20260930_native_elicitation.json for exact hashes, commands, JUnit
results, diagnostics and retained failures. These local results resolve the
observed Codex permission translation defect. Remote native capture and the
remaining M08/fixed-plan acceptance remain pending; no gate is closed.

## Remote capture from the applied lease - Core 0.2.43

Core a061960 adds the public native_approvals_from_lease composition option.
Hosts may construct a runtime before lease installation; the copied native
factory enables capture at launch only when the R4 context includes both
approval.decide and input.provide. A legacy context, missing action or partial
action set leaves capture disabled. The existing explicit opt-in keeps its
strict requirement for both actions. Neither option confirms a human decision.

Connector f49d48e opts into that mode through the public Core factory and calls
the public decision method with named operation/context arguments. Its existing
effect-free composition, approved selection, lease installation and dispatch
revalidation remain in force. Nexus adopts the same Core package.

The final installed Core passed 65 composition/runtime/lease tests with both
application packages absent, byte equality checks and pip check. The first
installed run passed 64 cases and failed one shared test-helper import; the runner
now exposes the test repository root, never src, and asserts Core still comes
from the installed wheel. The normalized package and embedded/remote import
smokes passed. Connector installed tests passed 78 cases.

The new loopback WSS cases exercise the automatic daemon, canonical event queue,
operator decision API, reserved control dispatch and receipt return for approval
and input, with both approval and denial. They use a technical native peer;
they do not qualify a real remote provider or separate hosts. Nexus 301ed04
passed 101 installed cases and 83 overlapping cases without Connector. Exact
artifacts and results are recorded in test_runs_20260930_native_lease.json.

Initial remote assertions incorrectly included schema_version in the frozen
native callback request; input denial expects cancel while approval denial uses
decline. The expectations now match the existing contract. An initial isolated
lease-renewal timeout did not recur in the unchanged standalone test or sequential
full campaign. Its cause remains undetermined and the failure evidence is retained.

The next real remote journey also needs the existing M03/M10 public onboarding:
the current daemon discovery does not accept persisted trusted roots, and the
CLI does not yet expose the R4 realization/configuration staging services.
These are fixed-plan gaps, not closed by the technical WSS cases.
