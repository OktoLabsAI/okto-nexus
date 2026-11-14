# Supplemental v11 presence reconciliation

This is a one-campaign correction to evidence interpretation, not a change to
the approved campaign, runtime, receipt, product, or frozen helpers. The frozen
final-presence helper refused `POSSIBLE_UNSELECTED_START`; that refusal remains
retained in `final-presence-original-refusal.json` and is never relabeled a pass.

The frozen predicate conservatively considers every plan/setup selection capable
of starting both components. This campaign's complete retained driver ledger has
exactly six returned selections: initialize, Nexus install/start/uninstall,
local plan, and local setup. Nexus stop occurred through the controller-owned
stop wrapper and its original public proof remains pinned. No Connector or remote
selection occurred. Connector state and operator home are empty. The sealed
controller contains one local setup reservation, no work streams or requests,
and only the local Nexus owner.

`reconcile_presence.py observe` verifies the original proposal and receipt,
frozen dependency hashes, all 35 retained evidence files, exact ledger and
artifact-name sets, and sealed checkpoint/collector. It reuses the original
Nexus physical-cleanup/uninstall check. Both exact tasks must be absent and
canonical inspection must report `stopped/NO_SERVICE_OWNER`; the exact loopback
port must permit an exclusive instantaneous bind. It checks evidence again after
observation. Only then does it exclusively create
`public/final-presence-reconciled.json` with status
`RECONCILED_LOCAL_ONLY_CONNECTOR_UNSELECTED_CLEANUP_CONFIRMED`.

`reconcile_presence.py close` requires that supplemental evidence and its exact
helper/reference pins, revalidates the retained history and checkpoint, and
exclusively creates the previously absent `public/closure.json`. Status is
`CLOSED_RECONCILED_CLEANUP_ACCEPTANCE_NOT_INFERRED`; the existing frozen gate
therefore continues to prohibit campaign replay. It does not create a controller,
query a database, invoke CLI work, start/stop services, or call a provider.

Both operations require the original four proposal/approval CLI options plus
`--reference evidence-reference.json --reference-sha256 <qualified hash>` and
`--expected-helper-sha256 <qualified hash>`. Execute only with the exact installed
campaign interpreter and original environment. Root review precedes execution.

The setup remains `INSTALLATION_UNCONFIRMED`, with `OBSERVATION_UNKNOWN` and
`DEADLINE120`, one unsettled new reservation, seven cumulative reservations,
zero **new observed** tokens and 89,473 cumulative minimum observed tokens.
Zero observed tokens is not proof of no provider activity or final billing.
Cleanup is not M1 acceptance. Port/task absence is instantaneous; the retained
Nexus process-exit proof supplies the historical physical exit observation.

Qualification: 27 synthetic offline fixture tests passed in one run. They cover
the successful supplemental observation/neutral closure and refusal of additional
selections, incomplete/unconfirmed returns, remote artifacts, changed/sealed
checkpoint scope, erased faults, settled-state substitution, present tasks,
missing physical cleanup, busy port, evidence changes during observation, wrong
closure evidence kind and evidence overwrite. The original helper's refusal is
reproduced with the same local-only fixture. No real observation or closure was
executed during preparation. This qualification does not claim exhaustive race
exclusion or authorize further productive work.
