# M05 — Approved configuration at the local Core boundary

Status: partial P5.1 integration. Automatic dispatch and M05/G1 acceptance remain open.

## Implemented

The Core host composed by the real serve lifespan now owns an approved-local-launch factory. EmbeddedExecutor.authorize_r4 uses it before acquiring Core stores. The selected candidate and workspace must match the persisted realization. An arbitrary caller environment cannot replace the approved configuration. Open derives auth references from that configuration and rechecks it before Core prepare.

The resolver joins the admitted session, binding, endpoint, profile, workspace, canonical realization and private local record. It verifies scope/revisions, active agent, current store epoch and embedded owner/generation, readiness, approval and quarantine state. It recomputes configuration, publication and root-proof digests, verifies the retained complete candidate and current binary fingerprint, and compares physical workspace/provider-home identities. Database authority is compared again after filesystem reads.

The environment callback uses the public Core child_environment API. It revalidates configuration before and after asynchronous secret resolution. Explicit provider references use the form `provider:ENVIRONMENT_VARIABLE`, resolved on this host. Missing values and Nexus credential values are refused. Ambient variables are not copied as provider secrets. The default resolver does not implement a vault backend; vault integration remains pending. Core owns child environment name/value restrictions.

Directly constructing an executor for a serve-owned host cannot bypass its approved launch setup. Containment remains available without requiring productive launch configuration to remain valid.

## Verification scope

The integration test prepares the local realization and binding through HTTP, issues the canonical grant, resolves/adopts the operation through HTTP, reserves dispatch, installs a canonical lease, acknowledges application and calls Core open. It exercises the configured environment callback separately because its technical native factory bypasses process construction.

Tests explicitly force execution qualification and local CONTROL_READY, and call reserve/begin themselves. They do not prove an automatic local dispatcher or a real-provider journey. Negative tests reject private-record, physical-root, binary, owner and profile drift before lease request/Core-store creation. Authority change during secret resolution and missing/Nexus credentials are also refused. Existing no-Connector and remote regressions are rerun against the installed wheel.

The source run initially failed collection because a test imported the authority builder from the wrong module; it was corrected before the final installed campaigns. The initial built wheel was superseded before installation to include the endpoint quarantine check.

Installed results: 78 passed in the affected regression and 36 overlapping cases passed without Connector. No failures or skips. pip check passed.

## Remaining fixed-plan work

Start an owned embedded outbox consumer, correlate and persist Core receipts/events, renew leases, reconcile retained sessions and enforce shutdown/capacity. Compose session tools and protected vault access, then run the complete local journeys with Pi, Codex and Claude and the required failure/restart cases. No readiness constant, milestone or gate is promoted here.

Core and Connector artifacts are unchanged. The Nexus wheel contains preexisting user UI asset edits, excluded from this commit and from UI acceptance. The existing dependency deprecation warning remains.

See [results](test_runs_20260930_local_launch.json), [artifacts](evidence/local-launch-artifacts.json) and [installed runner](run_local_launch_installed.py).
