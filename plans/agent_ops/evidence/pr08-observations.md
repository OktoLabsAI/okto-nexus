# PR-08 — explicit external observation admission

This milestone implements OBS-01 through OBS-04 and their operational bounds
in Nexus 0.3.3, on `feature/v0.3.3`. Connector 0.0.12 and Core 0.0.14 retain their
previous commits. The fixed R3 plan, its IDs and historical migrations 1–163
are unchanged. Migration 164 is additive.

## Delivered behavior

An operator approves an existing agent, source kind and workspaces. Registration
retry recovers the same source through a caller registration reference. A
canonical self-manager operates only within that approval. Instance IDs and
generations come from a durable installation allocator; external names, panes,
paths and hosts cannot establish identity. Multiple instances remain separate,
without inferred canonical-session correlation.

The new explicit `observations.manage_self` and `observations.publish` permissions
deny absent, null, malformed and non-boolean values. Existing permission defaults
remain compatible. OBS starts disabled and has its own settings and dashboard
settings section. It does not depend on runtime, attention or harness flags.

Opaque 15-minute `nxobs_` credentials are hashed at rest and have an immutable
source revision plus 1–100 exact instance/generation/workspace grants. Only the
literal POST `/v1/observations/activity` accepts them. Canonical management is
under `/api/v1/observations`; EPT, MCP, runtime and management audiences cannot
use the publisher credential. Renewal requires canonical authority. Material
source/agent/issuer changes permanently revoke old credentials, including
true→false→true permission and key-restore sequences.

One writer transaction validates current authority before replay, consumes
source/actor/installation quota, validates freshness, writes heads and emits
private observational events. Exact latest sequence/hash returns its original
receipt without renewing TTL or duplicating an event. Conflict, generation
rotation, expiry, revocation and reset cannot overwrite a newer head. Commit
failure produces no success receipt.

Freshness uses both receipt and observation age. Expiry projects stale, never
idle/offline/capacity availability. Revoked or disabled authority projects
unavailable while authorized historical reads stay passive. Source continuity
is aggregated independently across its instances. Completion references remain
observational and never complete work. Stable continuity reports do not create
a heartbeat event log; material state, blocking and completion changes do.

Admission bounds include 4 KiB per supplied/canonical report, 100 reports per
atomic batch, 512-character optional text, bounded token/source/instance counts,
durable aggregate budgets and a 32-slot ingress guard before body/thread/writer
queues. Existing retention handles observation events with independent age/row
bounds and bounded token/orphan-bucket cleanup. Live head replay fences and
referenced token evidence remain. Existing buckets are not deleted merely for
becoming full: a later rate reduction cannot accidentally refill spent quota.
Reset removes obsolete instance/token state, preserves the generation allocator
and surviving identities' quota, and clears orphan budgets.

Public usage and exact API semantics are documented in
[`docs/external-observations.md`](../../../docs/external-observations.md).

## Qualification and retained diagnostics

Original source reports and their byte hashes are recorded in
[`pr08-observations-tests.json`](pr08-observations-tests.json). Repeated runs are
not added together as independent cases. Their evidence covers strict syntax,
permission compatibility, audience separation, HTTP validation, passive reads,
100-instance batching, concurrency, durable revocation, reset, TTL, quotas,
retention and structural regressions.

The selected source reports contain **525 unique green cases** (535 records
with ten explicit overlaps). The installed qualification contains **14 green
cases**, recorded separately, plus **49 real HTTP assertions**. Neither is
added to the source count. All selected reports have zero failures, errors or
skips; the failed fixture attempt below remains a separate diagnostic.

The final non-editable Nexus wheel has SHA-256
`85a882cf1ee71ff953e3ce79a25216a1092d0b3a7e314b72527749267e07c130`.
All **486 Python, 164 migration and seven static files** have identical sets
and raw bytes in source, wheel and installation. Installed import origins and
Core 0.0.14 were checked explicitly. Real HTTP exercised source registration,
instance grants, publication/replay, audience refusal, feature disable/re-enable
after TTL and historical read. The canonical-table snapshot was unchanged,
excluding only explicit settings changes and auxiliary OBS state/events.

Chrome **156.0.8078.79** displayed all 16 OBS settings controls. Toggle and
source-burst changes persisted through reload, an invalid TTL disabled saving,
and the original false/20 settings were restored without changing other
settings. Light/dark screenshots and semantic snapshots were inspected. At
390 px the document width was also 390 px. This is browser/semantic evidence,
not a screen-reader-product campaign. The browser was closed and the isolated
Server returned canonical `DRAINED`; owner and launcher processes were absent.
Windows briefly retained TCP records with owner PID 0; a subsequent probe did
not connect, as recorded in the shutdown artifact.

The initial HTTP report contains eleven fixture setup errors: its call to the
existing `set_permissions` port omitted required `preset_id`. No HTTP product
case ran in that attempt. The corrected fixture passed all eleven cases, and
the final report passed twelve after adding the canonical-size boundary case.
That regression refuses an input fitting 4 KiB whose default TTL/UTC
normalization would exceed the stored report limit, returning 413 before SQL.

Storage's initial and directed reports precede the rate-retention correction;
the final 39-case report includes all prior cases and the correction. Retention
similarly retains its initial nine-case report and final ten-case report.
Audience's final ten cases repeat the corresponding cases from the initial
29-case run, using the final wiring and canonical `regenerate-key` route.

Fault tests inject event/storage/commit failures, including SQLite commit
failure; they do not fill the machine's physical disk. The suite also measures
rollback of state, events and budgets, and races publication with generation
rotation. Configuration bounds are declared limits, not measured throughput
capacity. A Starlette/httpx deprecation warning remains external to this change.

The frontend build passed TypeScript and Vite. The generated entrypoint loads
`index-FrvqCgS-.js` and `index-C1ejzFJK.css`. Vite reported the existing large-chunk
warning. The resolved `emptyOutDir` target was verified inside this repository
before building.

The first package helper invocation used Python `-I` for the build backend and
could not locate user-site build dependencies. It failed before producing a
wheel. The helper was corrected to build normally and assert installed import
origins explicitly; the failed invocation is retained as a tooling diagnostic.

The browser helper needed three corrections to its own assertions: a numeric
label gains the existing `modified` badge after editing; successful save reads
`Settings saved and applied.`; headed mode can have no explicit viewport.
Original helper versions and diagnostic snapshots are retained. The final
complete run passed, with no product changes. An initial header-menu click was
blocked by the first-run metrics opt-in panel, which was closed without opting in.

All 50 retained originals were checked against their Git-index byte hashes.
The staged generated JS, CSS and entrypoint match the qualified build bytes.
Ruff passed for the changed Python files; the authored-file whitespace check
passed after removing two trailing blank lines from the ledgers. Immutable raw
reports and generated JS are excluded from that whitespace check. The unchanged
large-bundle shader whitespace noted in PR-07 is not edited by hand.

## Remaining scope

The real installed Herdr schema, optional observer/helper and read-only Herdr
campaign belong to PR-09. External attention categories and canonical/external
correlation/precedence belong to PR-10. No terminal scraping, process control,
native evidence synthesis or inferred canonical correlation is delivered here.

These source/storage/HTTP/package checks do not qualify a real model provider,
external MCP client campaign, productive M1/M2, login supervisor or the joint
PR-10 campaign. Those existing named gates remain open in the ledger. No
personal service or credentials were used, and no package was published.
