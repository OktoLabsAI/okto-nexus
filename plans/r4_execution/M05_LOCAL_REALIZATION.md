# M05 — Approved local realization persistence

Status: partial P5.1 integration. M05 and G1 remain open.

## Implemented path

The existing realization route now accepts an embedded preparation request authenticated by an operator agent key. Its separate remote variant still requires a scoped execution ticket. Local preparation checks operator and represented-agent authority before filesystem access, selects the complete candidate retained by the serve inventory owner, verifies its fingerprint, and records the physical identity of the approved workspace and optional provider home.

Migration 083 stores the private local mapping and configuration in the Nexus database. Only protected secret references are accepted. Private and canonical realization records commit together; a failed insert rolls back the logical workspace and canonical evidence. Responses remain path-free. Repeated client intents require identical actor, request, directory identity and candidate. The record survives serve restart and generation change.

The existing binding prepare/apply routes approve the resulting canonical realization. Preparation does not create a session, issue a WSS ticket, initialize a Core runtime store or start a process. Runtime readiness remains RECOVERING until local dispatcher and lease integration are implemented.

## Verification

The public HTTP tests cover preparation, idempotent replay, binding approval, non-operator refusal before filesystem access, invalid consent/configuration, changed directories/binaries, owner and represented-agent changes during preparation, atomic rollback and serve restart. Discovery uses a technical candidate; credentials are fixture setup. This is not native-provider acceptance.

The installed runner compares source, wheel and installed package bytes. It runs outside the clones with isolated Python. The environment without Connector checks both module and distribution absence and passes pip check. It reuses the actual venv created for the preceding inventory increment, installing the new Nexus wheel; it is not a newly created environment for this increment.

The initial source run found a test expectation error: application validation correctly returned HTTP 400 for rejected consent while the assertion allowed only 409/422. The assertion now accepts the documented validation response. The final installed runs include the corrected test and restart case.

Installed results: 69 passed in the affected Nexus regression; 27 passed without Connector, overlapping that regression. No failures or skips. Package validation and pip check passed.

## Remaining work

Consume and revalidate the approved mapping at dispatch; install and renew canonical leases under the current local owner; publish receipts/events; integrate tools and recovery; execute the complete Pi, Codex and Claude journeys required by the fixed delivery plan. No milestone or gate closes here.

Core 0.2.38 and Connector artifacts are unchanged. The Nexus wheel includes preexisting user UI asset changes, which are not committed or accepted as UI delivery here. The dependency deprecation warning remains.

Results and commands: [manifest](test_runs_20260930_local_realization.json), [artifacts](evidence/local-realization-artifacts.json), [runner](run_local_realization_installed.py).
