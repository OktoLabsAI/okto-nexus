# PR-06 — approval, result and authority coverage

This increment continues the fixed R3 attention backend. The task/scenario IDs
and plan hash are unchanged. PR-07 UI, browser acceptance, real provider/client
campaigns and full R3 acceptance remain open. Connector and Core are unchanged.

## Canonical sources and commands

Generic approvals are projected through current canonical records, recipient
proof and the actual decision registry. Governance approvals have no invented
TTL; coordination receipts and binding proposals retain their original deadline
and scope. Legacy/orphan native approvals remain inspection-only. Decision
controls do not promise successful approved re-execution: a valid rejection can
remain possible while approval business gates fail. Canonical decisions accept
an optional strict revision, checked before handlers in the writer transaction;
failed re-execution returning to pending cannot make an older form current.

Manual/MCP handoff completion and rejection now appear as results. A proven
native execution and its handoff share one claim-epoch identity in either arrival
order. Seen state survives completion lag and partial native-result retention.
Independent native results keep their former identity and priority. Migration
162 transfers old preferences only through exact canonical links, preserves
the original rows, merges any seen mark and the furthest snooze, and advances
the revision. Timestamp ordering includes offsets and microseconds. Migration
161 and its anchor SQL are unchanged.

Delivery/recovery occurrences include the original message reference. Cleanup
includes the original result reference, and the canonical artifacts inspection
command can select a maintenance receipt directly, including DONE history and
records beyond the 100-row overview. It retains existing operator authentication,
origin/CSRF controls and explicit cleanup idempotency. The inspection selector
cannot request a mutation. Changing the aged-handoff threshold changes its
source revision while preserving the waiting episode.
Inspection also remains available to the current operator without an active
dispatcher or with harness execution disabled; mutations retain their owner
fence. Execution references include the executor required by the administrative
inspector. The existing scoped handoff read accepts an exact ID beyond its
1,000-row overview, so retained historical work remains reachable.

Authority covers pending managed messages/handoffs, queued canonical execution
and native requests. It revalidates sender/audience, current permission and
governance, source/initiator/responder proof, grants and runtime configuration.
Relay ancestry is bounded and metadata-only. Handoff notices retain the original
audience/permission checks and obsolete claim generations do not create an
authority incident. Productive budget checks apply to new work without revoking
the response to an existing native request. Pending native decisions revalidate
the opening grant and original actor as well as responder/send authority.

Expiry without an explicitly selected grant uses the latest expiry among
otherwise admissible candidates; an unrelated grant cannot move the episode.
Legacy managed-handoff IDs remain compatible with their prior viewing state,
while source revisions continue to fence current changes. Normal availability,
recovery, inventory and unapplied lease renewal are not proof of revocation.
Content guardrails remain on the command path and are not reimplemented as a
content-scanning attention classifier.

One verified limitation remains: global execution-feature off/on/off without
a persisted authority change reuses the blocking episode and viewing preference.
`test_global_feature_toggle_has_no_persisted_episode_generation` documents that
gap; its passing assertion is not acceptance of AT-08 recurrence. PR-06 remains
in progress pending that correction and the client reconciliation scope.

## Read bounds and independent review

Kind filters avoid unrelated source families before policy preparation. The
whole engine's query count is constant across one versus forty distinct agents,
profiles and endpoints, with 120 mixed occurrences across workspaces. Exact
counts and the scoped result remain consistent. The five-second budget includes
cooperative Python graph preparation; an interrupted preparation fails explicitly
and a following read recovers. This is not a preemptive wall-clock bound for
every individual Python instruction or a claim of unlimited scale.

Independent reviews covered generic decisions/CAS, maintenance navigation,
result preference migration and engine filtering/budget integration. Productive
effects remain in the original command paths. Existing authentication/audit
writes retain their established contract and are not presented as projection
writes.

## Initial evidence and corrections

[The source manifest](pr06-attention-completion-source-reports.json) retains
initial reports, original/normalized hashes, transformations and deduplicated
coverage. Report counts must not be added as distinct tests. The first core run
loaded old storage assertions while the root edited the test source, so its
rendered traceback can contain newer lines. That report remains historical
evidence and is excluded from consolidated final coverage; no source hash is
claimed for its test process.

Other initial failures were fixture or expectation issues: missing/nonexistent
columns, the unique pending-cleanup index, decision wiring replaced by app
bootstrap, canonical rejection notifications, missing workspace selection,
timezone syntax, snapshotting a WITHOUT ROWID table, and an INSERT without a
column list. The automatic handoff test initially waited for the terminal
receipt but not the separate canonical result projection; it now waits for
that result before asserting deduplication. The reports preserve those failures.

Older partial authority-classifier tests were replaced by canonical-admission
coverage in `test_attention_authority.py`. Their migration-161 storage proofs
were retained as direct assertions of state, counters, timestamps, rollback,
reentry, retirement, retention and reset. The new reset checks preserve original
configuration counters and spent grant quota.

All fixture identities, databases, HTTP clients and native peers are synthetic
and disposable. HTTP, MCP, SQLite, transactions and migration behavior are real;
these tests do not qualify a provider or a user's native service installation.

## Qualification status

**718 distinct behavioral cases passed; 0 skipped.** One additional passing
case records the known global-feature episode limitation, so the combined
manifest contains 719 distinct cases without treating that observation as
acceptance. Source reruns are not added to this installed total.

| Installed report | Passed | Failed | Skipped |
| --- | ---: | ---: | ---: |
| behavior, initial wheel | 270 | 0 | 0 |
| authority regressions, initial wheel | 130 | 0 | 0 |
| platform, initial wheel | 163 | 1 | 0 |
| decision regressions, initial wheel | 67 | 0 | 0 |
| transport regressions, initial wheel | 82 | 0 | 0 |
| affected result/storage/migration paths, final wheel | 43 | 0 | 0 |

The initial platform failure exposed a real compatibility gap: terminal handoff
rows can have a NULL `updated_at`. The result trigger/backfill now consistently
uses the stored `created_at` as its fallback, without changing the canonical
record or substituting GET time. Six new cases cover upgrade, insert and update
for completed/rejected records. The existing failed HTTP fixture passed unchanged.
Both failed and corrected reports are retained, with one synthetic key redacted
from the initial installed report and original/retained hashes recorded.

The final wheel SHA-256 is
`1e91b5983b0cbc87662e4dbce838d12de86c6e5df47f2f380970bd530c807b27`.
All 477 Python files, seven static resources and 162 SQL migrations match source
and installed bytes. Compared with the broad-qualified initial wheel, only the
result SQL adapter and its migration-162 block differ. The final 43-case run
requalifies all affected result, upgrade, storage and migration-runner paths,
plus the original failure; unchanged payload qualification is carried forward.

See [installed reports and distinct coverage](pr06-attention-completion-installed-summary.json),
[wheel metadata](pr06-attention-completion-wheel.json) and
[exact release differences](pr06-attention-completion-release-scope.json).
The [final checks](pr06-attention-completion-checks.json) verify the fixed plan
and every retained XML hash against both working files and the Git index.
Changed Python files pass Ruff; the harness module retains its four preexisting
unused-import findings and introduces none. Ledger scope and staged whitespace
checks accompany the milestone. PR-06 and full R3 remain in progress.
