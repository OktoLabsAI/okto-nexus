# Runtime event artifact implementation

Scope: preserve large native events without blocking the event stream. No
native operation is replayed to repair history. Small events retain their wire
format. Release branches: Nexus 0.3.1, Core 0.0.12, Connector 0.0.10.

## Ledger

- [x] Confirm installed failure: Pi journal contains 101970-byte tool result;
  embedded publication rejects it at 65536 bytes and cannot advance its ACK.
- [x] Shared deterministic payload references, hash validation and negotiated
  chunk transfer codec; journal remains the recovery source.
- [x] Server artifact store persistence and authorized, idempotent chunk ingress.
- [x] Local and remote publication upload content before publishing references.
- [x] Resolve payloads for result projection and authorized terminal replay.
- [x] Regression tests: boundaries, Unicode, restart/replay, missing/corrupt
  artifacts, cross-session access, remote transport and independent streams.
- [x] Build Core/Connector/Nexus wheels and source distributions; install all
  three wheels together in an isolated Python 3.13 environment; dependency
  compatibility check passes. Both consumers pin Core 0.0.12.
- [x] Read-only replay check of all 64 retained Pi events from the reported
  incident: five large payloads (101649..171320 bytes) round-trip exactly through
  the reference/chunk codec. No live journal or session was changed.
- [x] Installed integration campaign: Nexus 41 passed (artifacts, ingress,
  replay, three adapters, public WebSocket integration and backup), Core 24
  passed, Connector 41 passed; 106 installed-package tests passed in total.
  Nexus evidence: `build/event-artifacts-installed-evidence/campaign.json`
  and `tests.xml` in the same directory.

Artifact storage is private to the authenticated execution session. Content is
stored using the existing ArtifactStore port; transfer staging is bounded and
durable. A transfer acknowledgement never acknowledges the event sequence.

The inline threshold remains 64 KiB. The shared payload ceiling is 16 MiB;
native framing and bounded queues now admit payloads destined for external
storage. The existing runtime artifact quota covers both result artifacts and
event artifacts, and maintenance inspection reports their reserved bytes.
These are private session artifacts, resolved only after session authorization;
they do not become public agent-authored catalog entries. Offline backup copies
and validates their referenced payloads. Abandoned incomplete transfers expire
after 24 hours and can be reconstructed from the unacknowledged journal.

Validation does not qualify a model provider or a second physical host. Local
and remote paths use the real application/transport with synthetic native peers.
The currently running Nexus installation has not been replaced or restarted.
