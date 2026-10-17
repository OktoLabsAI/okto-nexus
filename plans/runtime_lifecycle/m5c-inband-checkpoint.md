# M5c authenticated prelease refusal checkpoint

The original `runtime.open` can fail during Connector candidate discovery before an initial lease exists. A binding-scoped receipt ticket alone cannot authorize this terminal fact. This checkpoint adds a negotiated `nexus-startup-refusal-v1` request on the authenticated control channel. Core validates the immutable original refusal, no-effect receipt, channel identity and exact released capacity proof. The Server checks the current `CONTROL_READY` owner, canonical pending session, original dispatch grant, absence of a lease/native action/event and correlated capacity in the receipt transaction. A duplicate report/ACK is idempotent. Generic HTTP publication still requires its original applied-lease proof.

The Connector persists a prelease marker, original refusal and terminal report before publishing it. Its generic receipt replay excludes prelease reports. A candidate-discovery failure is isolated to that session and the next handoff can use the same control connection. Post-lease startup preparation retains its prior path.

Core: `2cefaa9` on `feature/v0.0.12`. Connector: `9093b86` on `feature/v0.0.10`.

Source checks: Core 29 targeted cases, Connector 68 transport/publication/execution cases, Server prelease channel case, and both candidate-discovery and post-lease preparation failures in a separate local Connector process. The candidate case delivered one terminal caller error, released capacity, kept the control link ready and delivered a follow-up handoff.

This is **not M5 completion**. A complete Connector process restart creates a new control generation. An unacknowledged prelease report from the old generation is retained durably but is not yet safely replayable through the replacement connection; reconciliation still needs a verified recovery path. Also pending: storage/crash cuts, forged/stale report matrix, installed-wheel campaign, uncertain-effect startup isolation, differential restart/revoke/reset, load, and major real UI gate. The global Nexus installation was not changed.
