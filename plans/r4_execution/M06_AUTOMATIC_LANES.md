# M06 — Automatic approved daemon lanes

The daemon now composes lane attachment and the execution owner from persisted approved bindings. Each lane uses its agent identity and checks authority before and after asynchronous resolution. Launch configuration and session capability composition use the approved launch provider.

The HTTP client remains owned during execution cleanup. Executor-scoped shutdown preserves unrelated runtimes. Tests cover identity/origin changes, revoked bindings, cross-connection frames, separate agent identities, canceled cleanup observers, and scoped shutdown.

Installed artifacts passed 336 Connector tests (one existing skip) and 81 Nexus tests (one dependency deprecation warning). The Nexus integration starts the actual daemon transport, attaches automatically, and exercises five canonical operations over HTTP/WSS. Native execution and protocol readiness are technical fixtures.

Evidence: [manifest](test_runs_20260930_automatic_lanes.json), [artifacts](evidence/automatic-lanes-artifacts.json), and installed campaign JSON/XML/logs. The original runner metadata retained an overly broad automatic-lifecycle limitation; the runner wording now distinguishes this tested initial startup from pending lifecycle work.

## Remaining acceptance

Bound ticket rotation, lease/capability renewal, nonempty reconciliation, restart recovery, native-login migration, and real-provider end-to-end journeys remain required. Connection teardown currently stops runtimes belonging to that executor. No milestone or release gate is closed.
