"""Write the final human-readable scope after the raw reports are closed."""
import json
from pathlib import Path

REPO = Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
reports = json.loads((REPO / 'plans/agent_ops/evidence/pr10-correlation/reports.json').read_text(encoding='utf-8'))
assert reports['collection_phase'] == 'closed_qualified_milestone'
benchmark = reports['benchmark_candidate_v2']
(REPO / 'plans/agent_ops/evidence/pr10-correlation.md').write_text(f'''# PR-10b — canonical correlation and shared diagnostics

OBS-12 and OB-19 are verified for the declared Windows/local contract. Joint
PR-10, the broader diagnostics tasks and full R3 remain in progress. The fixed
plan remains `20d0fafdedc793b97a277f5d41355d7d597ff724a77687394215eea3113ba996`.

The implementation adds operator-only correlation management, migration 166,
bounded CAS/tombstone storage, an existing-runtime Core birth reader, host-owned
Windows identity comparison, and passive canonical metadata in current OBS reads
and attention. The dashboard presents canonical facts before the separate
external signal. A last received receipt does not establish current activity,
liveness or capacity. Historical completions do not inherit later associations.
The external summary retains its previous meaning.

## Package and installed qualification

The final Nexus 0.3.3 V2 wheel SHA-256 is
`{reports['wheel_sha256']}`.
All 681 raw package files match source, detached build, wheel and installation:
505 Python files, 166 migrations, seven static assets and three other files.
Core 0.0.14 is unchanged, wheel SHA-256
`{reports['core_wheel_sha256']}`.
The [final package proof](pr10-correlation/candidate-v2/package-proof.json)
records every digest. [The delta](pr10-correlation/candidate-v2/package-delta.json)
contains exactly two changed attention modules; 679 files, including all seven
static files and the diagnostics implementation, are unchanged from V1.

Tests run outside the checkout in isolated user directories with per-test import
guards for installed Nexus/Core modules. V1 passed 736 distinct installed cases:
458 correlation, 203 regression and 75 diagnostics. V2 passed
[237 affected cases](pr10-correlation/candidate-v2/installed.xml): 217 repeat V1
identities and 20 new policy cases. The qualified union is 756 distinct identities,
including 519 unchanged V1 cases not rerun on V2; it is not a claim that 756 ran
on V2. Source reports overlap and are not added to this total. The source read
regression passed 114 cases. Frontend passed 130 cases and TypeScript/Vite built;
all 40 changed Python files passed Ruff.

The retained [reports](pr10-correlation/reports.json) preserve candidates, initial
failures, corrected retests and precise suite scopes. Build/test/collection
commands and import guards are in `pr10-correlation/drivers/` and the corresponding
qualification JSON. The [artifact manifest](pr10-correlation/artifact-manifest.json)
binds retained bytes, with verification against staged Git blobs before commit.
No private database, bearer registry or wheel is included in this evidence tree.

## Browser and measurement

The actual installed V1 HTTP/browser campaign passed eight checkpoints over
synthetic canonical data, preserving 13 canonical tables. Its 467 recorded GETs
contained no credential headers. Browser and Server cleanup completed. The
[browser manifest](pr10-correlation/browser/manifest.json) covers 230 original
entries. V2 keeps the same UI/HTTP projection files and static assets; its two
changed attention SQL modules have separate installed regression coverage. No
second browser campaign or real process/Core association is claimed.

The [first load campaign](pr10-correlation/benchmark/candidate-v1/assessment.json)
retains 90 samples: 86 succeeded and four hit the unchanged five-second attention
budget at 64 sessions / 4,096 correlated instances. No sample was retried.
Attention was loading correlations for working heads with no occurrence to
display. V2 reuses the exact current-head predicate to prune that preload and
registers the same SQL functions before policy construction, with cleanup even
if policy construction fails. Metadata, filters and the deadline are preserved.

The [V2 follow-up](pr10-correlation/benchmark/candidate-v2/assessment.json) used the
byte-identical driver and fixed workload: 1/64 sessions, 64/512/4,096 correlated
instances, half blocked and half working, 12 receipts per session, three samples
for each of five reads. It recorded **{benchmark['passed']}/90 successful samples
and {benchmark['attention_budget_refusals']} budget refusals**, without retries. Both
campaigns preserve canonical row fingerprints and show no DML/DDL in measured
read traces. They are separate measurements, not a general latency SLO or a
qualification of 4,096 distinct native sessions.

## Review, compatibility and remaining scope

Independent review fixed post-await authority/deadline gaps, malformed native
evidence reaching an OS read, receipt timestamps that could rank corrupt data
behind an older success, and JSON booleans/floats comparing equal to integer
scope revisions. Invalid receipt dates now make last-received metadata unknown.
Initial fixture/driver failures are distinguished in the reports: incorrect
process guard type, nonexistent bucket column, oversized pytest environment ID,
reason assertions, cold authentication query count, and the follow-up UDF helper's
missing timestamp. The first frontend loader failure has no standalone retained
report; the final 130-case XML is retained. Benchmark preflight's distribution-name
failure occurred before seed or measurement and is separately retained.

The API is additive. Missing, cleared, revoked or insufficient associations
project null and do not change canonical execution. Clear/disable through the
authorized API stops projection. Migration 166 is not destructively reversed;
retain the database and a supported backup before a binary rollback. Correlation
tombstones consume finite capacity and are not automatically pruned.

The five-second proof deadline is an admission budget, not a hard bound on OS
calls or SQLite commit latency. The batch's 32 MiB budget counts UTF-8 bytes of
fetched text columns including JSON; it does not bound serialized DTO size,
Python RSS or SQLite sort memory. Native association is initially local
Windows/embedded; unmatched and remote sources stay separate. Synthetic
browser/process data do not qualify actual Core process birth, providers,
native-service lifecycle, external-client cooperation, productive M1/M2 or full R3.

Shared diagnostic v1 is separately qualified in [Nexus](pr10-diagnostics-nexus.md)
and [Connector](pr10-diagnostics-connector.md), with unchanged legacy defaults.
Core is unchanged. Next implementation work is the remote identity/setup path;
the existing real-campaign authorization gates remain intact.
''', encoding='utf-8')

path = REPO / 'plans/agent_ops/evidence/pr10-diagnostics-nexus.md'
text = path.read_text(encoding='utf-8')
old = '''The same package also contains the OBS-12
candidate; its separate acceptance is recorded in [PR-10b](pr10-correlation.md).'''
new = '''This is candidate V1. The final OBS-12 V2 wheel is
`fc9bb8f075ac0167eee9c21d96592b12d46c218df77a0f2114f44b1fc20b1355`;
its [package delta](pr10-correlation/candidate-v2/package-delta.json) changes only
two attention modules. Diagnostics and all seven static files are byte-identical,
so the 75-case V1 qualification is retained with its original candidate label.
The separate OBS-12 acceptance is recorded in [PR-10b](pr10-correlation.md).'''
assert old in text
path.write_text(text.replace(old, new), encoding='utf-8')
print('Final PR10b and diagnostics scope written; R3 remains open.')
