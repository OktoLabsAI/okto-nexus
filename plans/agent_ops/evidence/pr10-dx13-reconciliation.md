# DX-13 reconciliation — existing Connections/Finish reuse

Date: 2026-11-06. This is a documentary reconciliation performed during PR-10,
not a new implementation or qualification campaign. DX-13 belongs to PR-03 and
PR-04. The fixed plan, milestone status, scenario inventory and outstanding
M1/M2/service campaigns are unchanged.

The [fixed plan, section 8.9](../../../PLANO_CODEX_NEXUS_INTEGRACAO_ATENCAO_ONBOARDING.md)
requires three things for DX-13: reuse Connections and Finish; retain the
normalization of the legacy `automatic_reply` field; and preserve an agent's
runtime policy when adding an external participant. All three have code and
existing test evidence. The previous `NOT_STARTED` entry omitted that reuse.

## Implementation trace

| Contract | Existing implementation | Existing verification |
| --- | --- | --- |
| Managed setup uses Connections/Finish | `frontend/src/components/AgentConnectionsPanel.tsx:240–250` calls `runtimeApi.finishSetup`; `src/okto_nexus/application/terminal_connection.py:237–262` uses the same `/connections/setup:test` and `/connections/setup:finish` routes. `src/okto_nexus/adapters/inbound/http/runtime_v1.py:1091–1110` delegates to the shared service. `src/okto_nexus/application/connection_setup.py:12–22,214–230,342–344` shares the outer UoW and records the canonical Finish receipt. | `test_finish_atomic_idempotent`; `test_review_requires_exact_consent_then_finish_and_reconnect_preserve_configuration`; `test_existing_agent_binding_is_reused_after_canonical_project_match`; `test_reconnect_reads_later_customization_without_reissuing_grants`; receipt recovery tests through both HTTP prefixes. |
| No independent automatic-reply option | `frontend/src/connectionConfiguration.ts:42,46` normalizes imported/exported configuration to `automatic_reply=true`. Core `src/nexus_connector_core/connection_configuration.py:69–70` normalizes the compatibility field. `connection_setup.py:191,324–328` exposes/enables the existing canonical behavior. | `tests/execution_r4/test_connection_setup.py:39–80` sends legacy `automatic_reply=False`, confirms normalization to true, a single binding/receipt after retry, and rejection of disabling the endpoint conversation policy. |
| Adding an MCP participant preserves managed runtime | `src/okto_nexus/application/participant_setup.py:12–42` authenticates the existing identity/workspace/method and prepares its context using a read UoW. It reads effective runtime policy without saving a replacement policy. | `tests/execution_r4/test_participant_init.py:58–102` first creates a managed binding, then applies and reconnects the participant. Its snapshot includes Finish receipts, bindings, endpoints, grants, execution policies and runtime overrides; all remain unchanged. Configuration and existing unrelated client entries also survive. |

The participant flow has separate local file/vault checkpoints. It does not
claim a distributed transaction with Finish or create an alternative managed
setup operation. The managed path continues to use the canonical transaction.

## Retained evidence

The reconciliation read the retained JUnit reports and checked the named cases.
It did not execute, copy, modify or combine the historical reports.

| Retained report | Recorded result | Relevance and limits |
| --- | --- | --- |
| [pr03-terminal-connect-installed.xml](pr03-terminal-connect-installed.xml) | 112 passed; zero failures/errors/skips | Includes managed Finish, binding reuse, reconnect and canonical HTTP recovery cases above. Installed packages outside the checkout; native build/probe/model responses were simulated. |
| [pr03-preset-evolution-installed.xml](pr03-preset-evolution-installed.xml) | 148 passed, 8 skipped; zero failures/errors | Re-exercises setup/recovery and managed reconnect. The eight existing dashboard browser cases are skipped, not accepted as passing. This overlaps other reports and is not added to a unique-case total. |
| [pr04-participant-init-nexus-installed.xml](pr04-participant-init-nexus-installed.xml) | 36 passed; zero failures/errors/skips | Includes 21 participant cases, two CLI regressions and 13 managed terminal-connect cases. The runtime-preservation case passed. Participant HTTP uses real FastAPI/auth/SQLite with an in-process wire adapter; vault is synthetic. |
| [pr04-participant-init-connector-installed.xml](pr04-participant-init-connector-installed.xml) | 80 passed; zero failures/errors/skips | Compatibility coverage for direct MCP configuration and approved MCP/native managed launch. It is not a real-provider campaign. |

The [project dashboard campaign](pr03-project-dashboard.md#real-browser-interaction)
also used real Chromium against an installed backend. Its recorded observations
at lines 47–58 show Connections displaying the terminal-created identity's
stored binding, enabled runtime and session context. Closing the panel preserved
these objects; subsequent personalization and terminal resume preserved the
identity/configuration and reused the same receipt. Native checks and provider
execution were synthetic.

Detailed original scope and qualification limits remain in
[terminal connect](pr03-terminal-connect.md),
[preset evolution](pr03-preset-evolution.md),
[project dashboard](pr03-project-dashboard.md) and
[participant init](pr04-participant-init.md). Their historical pending lists
describe those increments; later participant evidence may supersede individual
items. This reconciliation does not reopen or close those other tasks.

## Ledger conclusion and limits

DX-13 is `VERIFIED` for its three explicit contracts, with distinct managed and
participant subscopes, on the recorded Windows platform. This records existing
reuse and preserves the evidence's original qualification boundaries. No
production change was needed or made for this reconciliation.

This does not certify the current PR-10 wheel or turn the historical suites into
a new campaign. It does not complete PR-03/PR-04, productive local/remote M1, M2
with real cooperating clients/providers, initial remote identity provisioning,
native Windows service qualification, or the full R3 acceptance. No provider
inference or personal credentials were used by this audit. The fixed plan hash
and all task/scenario/invariant/completion-criterion inventories are unchanged.
