# M01 — native decision contract increment

Status: **IN_PROGRESS**. This increment does not close M01 or G0. It fixes a
concrete mismatch discovered while reviewing executable R4 conformance:
the preview required a prefixed hash inside the native operational proposal,
but the Core runtime produces and verifies an unchanged raw hexadecimal
native hash. Synthetic preview fixtures had hidden that mismatch.

## Implementation and artifacts

Core now preserves the complete native request, validates closed decision
payloads, uses a separate JCS digest for the R4 operational proposal and
checks input response digests before conversion. Runtime and wire conversion
share the native action classification and journal semantic. Receipt
projection verifies the actual typed operation and preserves possible-effect
classification when projection fails after execution. Notifications still do
not apply decisions. Native and historical R3 hashes remain unchanged.

The native subprocess campaign runs both the direct API and R4 conversion
paths for approval and input, with a real SQLite journal. It checks a single
native reply after replay, exact request preservation and rejection of
altered params, targets, response content and authority. This is technical
peer evidence, not a provider or application dispatcher campaign.

The R4 generator has a non-writing `--check` mode and a CI check. Generated
R4 resources use stable LF bytes. Public API documentation now covers all
R4/inventory exports and the current version. The bundle remains
`development-partial`, `R4_BUNDLE_EXECUTABLE=False`.

| Repository | Published change |
|---|---|
| Core | `9af7f01`: implementation and evidence; `598ec4c`: exact wheel publication |
| Connector | `ce91e7f`: exact Core pin and vendored-wheel packaging regression |
| Nexus | Enclosing commit: exact pin, lock, inventory version guard, vendored wheel and evidence |

Core version: `0.2.23.dev0`. SHA-256 of the identical wheel in all three
repositories:
`3b63c9e6be4ccd1c843f99753d997b5992affe85209b0e2e404ff2ccfab0c733`.
The sdist was built locally with SHA-256
`b2472462143513052eb3a2c06fefa7b44025384645800370436ec4fc45dd441b`.
Isolated `python -I` imported the installed package outside the clones and
verified the independent R4 manifest and public conversion exports.

## Executed checks

| Execution | Result and limitation |
|---|---|
| Full Core suite on Windows/Python 3.13.1 | 862 passed, 74 skipped, two documentation failures. Both failures fixed; all three public documentation checks passed afterward. No claim of a new full green run. |
| Installed Core decision/schema/native bridge checks | 65 passed; technical native subprocess, no provider credentials used. |
| Core clean-wheel verifier | Passed isolated resources/imports and existing embedded/remote consumer smokes. |
| R3/R4 generator checks | Passed; deliberate temporary R4 drift was detected without overwriting it. |
| Full Connector suite | 237 passed, two skipped, one packaging failure. Fixed selection of an old wheel from a sibling clone; both packaging checks passed afterward. |
| Nexus R4 suite with shared 0.2.23 artifact | 42 passed. Includes an in-process vertical test importing Connector source explicitly; not installed distributed acceptance. |
| Nexus broad baseline before pin update | 831 passed, 71 skipped, ten failures; stopped at the configured failure limit. |

The first Nexus 0.2.23 check exposed its separate pinned inventory-version
guard still at 0.2.22. Updated that guard and the byte-verification fixture
with the package/lock pins, then reran the entire R4 suite successfully.

## Broad Nexus baseline defects still to resolve

These are internal implementation/test alignment work, not environmental
blockers. Preserve each original test's purpose when updating its transport.

| Failing tests | Required follow-up |
|---|---|
| `test_upgrade_from_64_preserves_identity_and_is_idempotent` | Verify all additive migrations and preserved identity; the legacy assertion expects only migration 065. |
| `test_disabling_mcp_fences_an_already_authenticated_stdio_connection`, `test_actual_stdio_self_discovery_and_connect_use_existing_serve_owner` | Exercise revocation/self-discovery through real MCP HTTP after stdio removal; retain a negative old-entrypoint test. |
| `test_no_comm_preset_mcp_tool_and_surface_revision_is_33`, `test_ts11_surface_revision_feature_flag_and_budgets` | Reconcile the actual surface revision 60 with fixed expectations of 59 and preserve feature/identity assertions. |
| `test_s2_every_tool_description_is_compact_single_line`, `test_s2_every_tool_parameter_has_a_description` | Fix the overlong harness_list description and missing parameter descriptions using US English. |
| `test_s4_cuttable_surface_meets_40pct_reduction_gate` | Investigate the measured 32.39% reduction versus the required 40%; do not lower the threshold to manufacture a pass. |
| `test_harness_open_claude_code_attach_requires_target_pid`, `test_harness_open_rejects_backend_for_claude_code_attach_substrate_over_rest` | Review legacy attach admission/profile fixtures and actual API restrictions; keep conditional attach qualification and pre-effect refusals. |

## Next implementation requirements

Finish M00 criterion-level review and measured budgets. Continue M01 with
public targeting facts, grant/context installation/revocation conformance,
all operation/error paths and the complete public installed-consumer
campaign. Then integrate canonical admission and dispatcher callers in
M02–M06. Neither helpers nor passing preview tests close those product tasks.
