# Explicit control-link closure on heartbeat storage failure — October 2, 2026

Historical Linux/Python 3.12 NS14 CI raised a normalized `DB_ERROR` while the
heartbeat tried to acquire SQLite's writer lock. That exception escaped the
accepted WebSocket handler without a protocol close frame. Controlled tests
reproduced that handler failure for both normalized and raw SQLite exceptions.
They inject the error at the heartbeat update in an otherwise real transaction;
they do not reproduce the original lock starvation or its timing.

The heartbeat path now closes with code 1011 on storage failure, or 4403 on a
domain authority refusal. It sends no database details and does not retry the
frame. Existing pump draining and scoped owner/lane/ticket release still run.
No busy timeout, lease duration or admission rule changed.

The new tests require an explicit close, one attempted heartbeat update, no
diagnostic text on the wire, unchanged connection generation, owner release and
zero execution operations. The store is available for cleanup in this campaign.
Persistent storage failure during cleanup remains a separate unverified case.

## Verification and development artifacts

Six directed source tests passed. A fresh isolated frontend/package build and
installed campaign passed **19 tests in 55.15 s** on Windows/Python 3.13.1,
covering heartbeat failures, transport/ticket fences, lanes, reconciliation,
Core leases, expiry and authority changes. Campaign inputs were unchanged and
all three installed package trees matched the pinned wheels.

- Nexus wheel SHA-256: `65c9127c5ee4ac90d93627d907cdc32404db07f0fe9c254b9ba4effba3cbd5d2`.
- Nexus sdist SHA-256: `8b0d32e65921a29b76086b75af08a3c99e119db09bafccedfdabd18ff8b4da02`.
- Core and Connector wheels are unchanged.
- [Campaign](evidence/ci-link-storage/campaign.json),
  [JUnit](evidence/ci-link-storage/tests.xml),
  [installed package hashes](evidence/ci-link-storage/installed.json),
  [build manifest](evidence/ci-link-storage/build-manifest.json).

The corrected pre-fix failure report is `before-corrected.xml`. The first
`before.xml` used an incorrect fixture WebSocket URL and was rejected before the
fault; it is retained but is not evidence for the defect.

NS14 load starvation is still open: explicit closure makes the failure honest,
but does not establish channel progress under concurrent writes. Hosted full
regression, Connector timeouts, UI completion, final immutable artifacts,
independent-host/platform/provider acceptance and G0–G3 remain open. This wheel
is another development artifact, not the final M13 freeze.
