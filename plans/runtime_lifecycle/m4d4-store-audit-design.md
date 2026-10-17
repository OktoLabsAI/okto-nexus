# M4d4 — Storage-owned journal registration and audit frontier

Status: Core creation-registry foundation in development; full audit mechanism
not implemented or qualified. Follows M4d3. The existing
`EmbeddedSessionCatalog.audit_files()` must remain on startup until the
replacement below is implemented and its crash boundaries are qualified.

## Evidence from current composition

`EmbeddedDispatchOwner._execute()` registers the canonical Server session name
before authorization. `EmbeddedRuntimeHost._compose()` opens the shared owned
slot ledger and then creates a journal per executor/session. The canonical name
is useful for exact attribution, but is stored in the Server database rather
than at the host that owns the physical files. It does not independently prove
that every physical journal was registered, especially after a partial restore.

Connector's `CoreRuntimeHost` instead owns one shared journal and one slot
ledger. It already avoids the per-session directory enumeration, but sharing
its physical layout with Nexus would couple their journal writers. Moving all
Nexus history into that layout is not justified without isolation, crash and
latency measurements. Preserve both layouts while sharing lifecycle policy.

## Required ownership boundary

Introduce a Core-owned registry port backed by its installation storage. A
host registers an immutable journal location before creating/opening it for
productive use. The trusted host supplies the layout and identity; tool or
protocol payloads cannot supply filesystem paths. Per-session entries bind an
exact executor/session; a shared-host entry declares that layout explicitly.

The registry is physical creation intent, not a duplicate operation ledger and
not proof of native execution or release. Canonical Server operation/session
identity, Core claims, launch evidence, leases and occupied capacity keep their
current responsibilities. A registered but absent file cannot be assumed safe
if any corresponding native ownership remains uncertain.

Registration and audit metadata should use the existing owned-slot storage
adapter, with bounded reads and transactions. Account for registry growth in
the store budget; a storage-full error must retain prior evidence and cannot
turn into an empty registry. Compare metadata cost at 1k/10k/100k entries before
adopting the default. No unbounded in-memory directory map or duplicate native
claim table is needed.

## Initial conversion and subsequent startup

1. Keep productive admission fenced while the existing store is first audited.
   Import exact canonical locations in committed batches. A crash resumes the
   imported batches; it may repeat cheap filesystem enumeration but cannot
   repeat completed journal validation as though it were new work.
2. Validate directory entries, sidecars, occupied slots and the store identity.
   Unattributable ownership blocks the host; a known session's bad history is
   scoped to that session/agent under the existing recovery rules.
3. Commit the first audit frontier only after the whole pre-existing store is
   covered. A revision check rejects concurrent/unregistered creation. Normal
   registration after the frontier is durable before productive composition.
4. On later boots verify the same physical store identity, registry format and
   creation discipline, then enumerate occupied resources and unresolved
   creation intents by bounded indexes. Do not enumerate all retired journals
   or hold admission for their history.
5. Retain a bounded background directory audit. Unexpected files, missing
   registered resources or a changed store identity invalidate the appropriate
   frontier and surface a technical diagnosis. Never silently delete them.

A frontier must not survive an unverified restore/copy of only one component.
The implementation must define how the Server database and physical host store
detect that mismatch, including an explicit invalidation path for reset and
restore. A path, mtime or a boolean `audited` flag alone is insufficient.

## Qualification before removing the old startup scan

- Crash after registration, journal creation, productive claim, audit-batch
  commit and frontier commit; retry the same immutable identities.
- Cancel observers during storage work; retain the producer until completion.
- Missing/corrupt registry, missing ledger, unexpected file/sidecar, scope
  conflict, partial restore and storage-full/locked errors preserve evidence.
- Occupied native resources override any history checkpoint or audit frontier.
- Same pending work with 1k/10k/100k retired sessions: measure first conversion
  separately from subsequent boots, including files opened and SQL work.
- One held journal does not delay independent ready-agent admission; shared
  ownership corruption still blocks the host.
- Qualify Nexus per-session and Connector shared-journal composition with the
  same Core registry contract before coordinated deployment.
- Run the large milestone through disposable Nexus UI/Meta-harness scenarios;
  retain the existing quota restriction on new real Codex provider calls.

This design does not close scan-cap removal, stream scheduling fairness, the
M5 differential lifecycle campaign or the M6 supervisor decision.
