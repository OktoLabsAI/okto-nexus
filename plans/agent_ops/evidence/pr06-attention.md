# PR-06 — operator attention backend, first increment

The fixed R3 scope is unchanged. This increment adds the twelve initial kinds,
the operator read API, shared viewing preferences and SSE invalidation. PR-06
remains in progress: authority-blocking detection currently covers managed
handoffs, with other pending message/native paths and policy gates still open.
Approvals without a native request are not projected; native approval evidence
does not certify the broader wording of AT-01. PR-07 UI/browser acceptance has
not started. See [the contract](../../../docs/attention.md).

## Implementation and review

List, totals and summary derive from one filtered SQLite relation inside a read
transaction. Pages use stable keysets and a material snapshot fence. Policy
facts are read in batches; pure projectors never run admission, consume leases,
create decisions or perform per-occurrence service calls. Processing has a
five-second budget, including policy preparation, and fails explicitly.

Native request classification shares pure authority predicates with canonical
commands. Existing authentication, audit, CAS and dispatch wrappers remain in
place. Tests mutate 27 real authority facts, compare six lease-renewal mismatch
cases, and verify the command/projection agreement. The grant expiry predicate
now compares instants, fixing equality across `Z`, `+00:00` and `-03:00`; a real
delegated grant exercises the shared authorization wrapper at these boundaries.
Canonical archival closes the attention occurrence even though the native
request and approval status can remain pending, preserving its ID and history.

Migration 161 adds viewing preferences, source-linked episode metadata and two
nullable cleanup diagnostic columns. Write-time anchors commit/roll back with
their source. Backfill is first stored observation, never a reconstructed past
transition. Grant/configuration anchors avoid moving an episode on retries or
health-only observations. Source deletion removes only that source's anchor.
Seen/snooze is shared by the existing operator principal, fenced by source and
preference revisions, and does not change canonical work. Preferences are not
age-pruned while their source results can still be retained.

The existing SSE route gains `view=attention`. Every connection requests a
snapshot; batches emit one metadata-only invalidation, without native token
payloads. Retention gaps include cursor-zero insert-and-prune races. Revocation,
logout and feature disablement clear protected content; source failures preserve
the last authorized view as stale. SQLite failures in projection policy reads,
stream bounds and live cookie revalidation return sanitized errors. Ordinary
legacy stream behavior remains separate. Bounded refresh (at most 15 seconds)
also covers time changes and cross-device preferences without a domain event.

## Source evidence and initial failures

The source-report manifest retains original and stored hashes, XML counts and
any transformations. XML trailing whitespace is represented by character
entities with parsed content preserved; valid synthetic API-key tokens are
redacted only when present, with counts recorded. Source reruns overlap and
must not be summed as independent cases.

Retained initial failures include:

- Settings accepted booleans/fractions as integers; the new attention thresholds
  now enforce their intended strict type without changing older settings.
- An HTTP fixture entered the same application's lifespan twice to model two
  devices. The second device now shares the already-running server; real
  independent clients and preference persistence remain exercised.
- The first storage retention fixture assumed message deletion cascaded to
  deliveries. It now follows canonical deletion order, preserving the actual FK.
- Four query-error tests expected HTTP 500; the established `DB_ERROR` mapping
  correctly returns 503. Expectations were corrected without changing the
  sanitized failure/passivity assertions.
- Three pre-fix authority timestamp tests reproduced age drift after retries or
  observations. Source-linked configuration anchors fixed those cases. Directed
  follow-ups also cover retirement without revision and both history-reset modes.

One initial native test run (six successful tests and one teardown error) was
overwritten before collection; no initial XML is claimed. A monkeypatch blocking
database/clock access during pure projection remained active during lifespan
shutdown. Scoping that patch to the projection fixed test isolation. The final
native reports are retained. Independent review also found and fixed archived
approval actions, textual grant-expiry comparisons and unhandled SQLite errors.
Review findings are distinguished from retained failed test reports; no
fabricated pre-fix test artifacts are supplied.

## Qualification boundaries

All identities, native peers, keys, homes and databases used here are synthetic
and disposable. SQLite, HTTP routing, TCP SSE, concurrency, migration and
shutdown behavior are real. An ASGI HTTP test is identified as such rather than
presented as a browser or provider campaign. No personal installation, service
registration, provider inference or published package is involved.

Current classifier limits remain explicit: authority attention covers admitted
managed handoffs, not every message/native gate; ordinary CLAIMED/silence,
offline-without-work, automatic cleanup and ineligible/dependency-blocked open
handoffs are not incidents. The aged-handoff eligibility predicate can inspect
multiple candidates inside one SQL query; this avoids query N+1 but does not
claim constant computation at large populations. Budget exhaustion is an error,
never an incomplete successful count. Resolved non-native conditions disappear
when their current source condition ends; attention is not another incident
history store. Initial cookie authentication remains in the existing middleware.

Client reconciliation, stale rendering, protected counter clearing, focus,
keyboard/light-dark behavior and canonical controls in the attention page still
require PR-07 implementation and real browser evidence. Native user-service
campaigns, qualified external clients, productive M1/M2 and full R3 acceptance
remain open. Connector/Core are unchanged in this increment. Operational rollback
uses `feature_attention=false` while retaining additive schema 161; older binaries
correctly refuse that newer schema rather than destructively downgrading it.

## Installed validation

**462 distinct cases passed; 0 skipped.** Each group ran with Python `-I` in a fresh wheel environment outside the checkout.

| Report | Passed | Failed | Skipped |
| --- | ---: | ---: | ---: |
| `pr06-attention-behavior-installed.xml` | 171 | 0 | 0 |
| `pr06-attention-authority-installed.xml` | 130 | 0 | 0 |
| `pr06-attention-platform-installed-initial.xml` | 160 | 1 | 0 |
| `pr06-attention-platform-recovery-installed.xml` | 1 | 0 | 0 |

Wheel SHA-256: `8642d7ed8b3fe51a7cd9bb72f9f79452c638b9aea124ef7e29ea6c1403418824`. All 470 Python files, 7 static assets and 161 SQL migrations match source bytes. Installed dependency compatibility, changed-file Ruff and ledger/diff checks are recorded with the milestone. The recovered platform case replaces its initial failure in the distinct total; source reruns are not added. The initial installed failure was a missing copied fixture file, `tools/offline_runtime_backup.py`, loaded by the existing reset/backup test. Copying the unchanged procedure into the isolated test tree fixed the one case without any package or test change. Both reports are retained.

Final staged diff-check found a trailing blank line in the query adapter. The release wheel removes only that EOF whitespace; all other package payloads are identical, and the changed module has identical parsed Python syntax. The release was reinstalled and every payload checked against current source and installed bytes. The 462-case qualification is carried forward without a redundant behavioral rerun; hashes and exact scope are recorded in `pr06-attention-release-scope.json`. A narrowly scoped Git attribute preserves exact XML report bytes across platforms so their retained hashes remain verifiable.
