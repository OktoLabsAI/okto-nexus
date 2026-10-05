# Explicit binding replacement

Nexus 2a37eda and Connector 4cb5ccf; Core 9c77871 / 0.2.44.dev0 unchanged.

## Public request and confirmation

BindingPrepareRequest now accepts optional replace_binding_id. This is an additive HTTP field implementing the existing NS05.05 rebind requirement. Without it, same-scope aliases still conflict. The reviewed proposal identifies the binding and previous revision/realization, and the new realization. Apply still requires the exact diff hash and applicable operator proof.

Replacement preserves agent, executor, workspace, adapter, alias, endpoint and profile. The target must have no session outside CLOSED; failed or uncertain claims require reconciliation first. The same target checks run at preparation and application. A changed binding revision or source authority refuses the reviewed proposal.

Apply updates only the realization references and binding revision under the existing writer transaction. Endpoint/profile and global agent authorization/configuration/credential revisions remain unchanged. Other bindings and their durable claims are preserved. The proposal retains the previous target snapshot and durable application result for repeat confirmation.

## Connector

bind prepare --replace-binding-id BINDING_ID selects the explicit local target. The Connector persists its snapshot before sending, validates it before subsequent network calls and accepts only the next binding revision with the same identity scope. A lost Server acknowledgment can recover the same application.

Local state schema 12 adds optional replacement selection, target snapshot and historical application result. Schema 11 records migrate with no implicit replacement authority. Upon acknowledgment the prior intent becomes SUPERSEDED; bind show/list and runtime selection use the current alias. Historical application replay returns the original result without another Server mutation.

The installed TCP journey exposed a stale administrative ticket after the first binding application. The daemon now compares current canonical identity authority before another realization publication and obtains a fresh derivative through the persisted registration when required. This refresh does not replace the existing control connection or retry a native operation.

## Evidence and remaining acceptance

Final installed verification passed 196 Connector tests and four TCP/HTTP/WSS journeys. The earlier campaign passed 34 Nexus cases on the same Nexus wheel and retained the stale-ticket failure; counts overlap.

See test_runs_20261001_binding_replacement.json for installed artifacts, commands and results. Server tests cover positive replacement, exact diff confirmation, changed revisions, foreign alias selection, active/uncertain target refusal and preservation of another seeded claim. Connector tests cover state migration, target drift, lost acknowledgment and historical replay. The TCP CLI journey performs actual registration, local realization, replacement preparation, operator decision and application.

The unchanged Core is verified by artifact hash. This increment does not demonstrate a new real-provider native opening after replacement, nor complete drift/login diagnostics. The unrelated active-claim preservation test uses a seeded durable claim, not another running native process. NS05.05 and the release gates remain open.
