# M07 — Durable Connector receipt publication

The Connector reserves a publication obligation before invoking Core, writes the exact projected R4 receipt before HTTP publication, and removes it only after the HTTP client validates the Server acknowledgment. The retained operation producer owns all three writes. A failed write or lost response fences the connection and preserves the unresolved obligation.

Startup reads ready receipts in pages of 128, obtains fresh per-binding authority, and republishes the original bytes before connecting the control socket. It preserves the source connection and generation used for the original authorized dispatch. A ticket obtained during recovery can be reused for lane attachment in the same startup attempt. Recovery checks the approved Server origin, binding, identity, credential epoch, authorization revision and ticket deadline. It never invokes discovery, prepare, open or another native effect.

## Persistence and limits

A separate additive schema-1 SQLite file sits beside the Connector state file, with suffix .r4-publications.sqlite3. It stores scoped operation IDs, action, intent hash, source provenance and projected receipts. It does not store operation payloads, operator input, provider environment or ticket material. Transactions use FULL synchronization. Admission is bounded to 4096 unresolved records across the store and database growth to 65536 pages. Acknowledgment frees rows for reuse; the Core and Server retain the authoritative operation history.

A reservation with no projected receipt remains unresolved. The empty-reconciliation proof checks this store and refuses readiness if any obligation remains. A crash after the Core effect but before receipt projection therefore cannot silently become an empty recovery report or permission to repeat the effect.

## Tests

The installed campaign is recorded in [the manifest](test_runs_20260930_publication.json), with [artifact hashes](evidence/publication-artifacts.json). Tests cover reopen, capacity, scope mismatch, corrupt receipt digest, payload exclusion, disk failure before effect and after effect, cancellation while a publication write is still owned, startup ordering, revoked/changed authority, lost acknowledgment, ticket reuse and 257 ready receipts across multiple pages.

The Nexus integration uses the real HTTP/WSS ingress, installed Core and Connector, and a technical native peer. Five canonical actions execute once. A close receipt is recovered after either failed delivery or loss of the committed response; the Server retains exactly five operations and five receipts. The prior ticket expiry is injected explicitly to obtain fresh authority. Product readiness is enabled by the existing technical fixture.

Initial source test failures included use of a system Python with an old Core, a test expecting release before the new durable acknowledgment finished, incomplete/shared fixture state in the startup test, and an assertion expecting historical receipt ingress to reconcile a disconnected session. These were corrected in the test setup/expectations; final installed results are authoritative. No application state was promoted to readiness to hide a recovery limitation.

## Remaining acceptance

- This recovers already-projected Connector receipts. Recovery of an unprojected reservation from Core facts still needs the durable Core-to-wire hash mapping.
- Nonempty claims, session adoption, event replay/watermarks and full control reconnection remain pending. A historical close receipt is accepted as operation history; after disconnect it does not automatically close the Server session.
- A still-live bound ticket refuses replacement. The obligation remains pending until usable authority is available; ticket rotation remains part of M06.
- Embedded publication recovery, process-crash campaigns, disk pressure, the complete provider/platform matrix and M00–M13 acceptance remain open.
- No milestone or release gate is closed. The shared Core stays at 0.2.34.dev0, with SHA-256 67de77b9250fc773887bd4d0f9c2c0cd5ea4af6ee0b433d38d837e58de7018ba.
