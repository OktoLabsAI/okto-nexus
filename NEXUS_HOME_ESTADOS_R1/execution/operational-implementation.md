# HST005–010 operational projection milestone

Implemented as a negotiated read-model extension. Presentation 1 uses the
unchanged legacy blocking reducer and historical placement. Presentation 2 uses
typed optional session/runtime facts, a separate pure reducer, complete canonical
relations before visual filtering, version-bound cursors and scoped page APIs.
Root owns route/service negotiation and the frontend; no Core/Connector change
is included here.

## Files and behavior

- `domain/home_entries.py`: optional SessionRuntimeFact relation and private
  operational source coverage; no productive entity/table or new authority.
- `adapters/outbound/sqlite/home_entries.py` and `home_operational_facts.py`:
  bounded constant batch queries for scoped sessions, last/effective lease,
  opening receipt, current binding/realization/endpoint, current executor owner,
  subject recovery and contiguous stream coverage; native dependencies and their
  exact decision/write operation and latest receipt metadata. Result membership
  receives `delivery_presentation_version` only as an internal SQL parameter.
- `domain/home_operational_status.py` / `home_harness_blocking.project_v2`:
  separate connection/activity/user-blocking dimensions. Agent-directed requests
  do not become operator obligations. Only the exact Codex requestUserInput
  contract supplies a blocking boolean; Pi/Claude and unsupported methods retain
  unknown blocking while canonical actions remain available.
- `domain/home_harness_board.py`: one connection card across Active/Needs you;
  independent requests and deliveries retain original context. A shared request
  cannot be incorporated by an arbitrary blocked owner. Full pending counts are
  distinct from previews/visible reminders, and full sessions/requests are
  separately pageable by exact card. Indexes over complete in-memory relations
  avoid scanning every session/request again for each card. Board semantic
  revision includes state/ownership/relations, not changed receipt arrival time
  alone; relevant lease/request expiry contributes a refresh deadline.
- `domain/home_entry_pages.py`: optional version 2 revisions/bindings and enriched
  SessionRuntimeFact refs; old SessionContext refs retain their four-field shape.
  Related cursors from a v2 harness child use the real v2 entry revision and are
  accepted by the matching versioned related endpoint, rather than looping on
  an impossible revision conflict.

## What establishes readiness here

An applied unexpired lease or a READY row alone is insufficient. Runtime-ready
requires the exact admitted runtime.open's SUBMITTED/SUCCEEDED receipt with
native_id, matching session/open scope and owner/binding revisions, applied lease
and current control owner/generation, enabled approved endpoint/subject and ready
workspace/realization, no recovery, no pending close and no known stream gap or
unprojected contiguous data. Core's open receipt bridge validates the selected
launch and native-open semantic; the Server receipt projection explicitly uses
that receipt to make the session READY after handle registration/event-pump
startup. This is a scoped runtime readiness/control contract, not process ALIVE.
The public SessionView may still report process and ownership UNKNOWN.

Idle additionally requires persistent session policy, complete pertinent
relations, all open sessions accounted for, no productive pending/uncertain work
and no human action. One-shot/closed sessions do not become Idle. Registered
configuration, host heartbeat, a lease without opening proof or unknown source
coverage cannot synthesize Idle. Independent positive work can survive an
unrelated unavailable external source; unknown totals are explicit.

The canonical embedded positive test uses real HTTP binding/grant/runtime.start,
the real Core runtime with an inert NativeFactory and a real persisted opening
receipt. Home reads leave native.opens at one; SessionView's physical-process
fields stay UNKNOWN. This proves the synthetic-peer HTTP/SQLite contract, not a
native binary's liveness or a current provider campaign.

## Decision registration versus application

Confirmation references bind request, decision, original productive operation,
session and epoch. An old RUNNING received after the decision cannot discharge
confirmation. Needs you placement for confirmation additionally requires current
runtime proof, complete pertinent coverage, no unknown open session and no
independent productive pending work. Stale/offline or insufficient prior proof
uses monitoring_unconfirmed instead of claiming a current full human block.

Native write FAILED/CANCELLED with possible_effect=0 emits
`NATIVE_RESPONSE_NOT_APPLIED`, no new response action and no applied/resumed
claim. OUTCOME_UNKNOWN/RECONCILING emits
`NATIVE_RESPONSE_OUTCOME_UNKNOWN`; SUCCEEDED write still emits
`NATIVE_APPLICATION_UNCONFIRMED`. Existing canonical inspection/recovery and CAS
retain authority; there is no replay or new write endpoint.

The unresolved native qualification subcase is **positive same-execution causal
application/resumption after an answer**, where the adapter/producer offers no
correlated acknowledgement or causally ordered progress fact. Neither receipt
arrival time, 202, native write success nor sequence greater than the original
request proves it. No marker or watermark is fabricated. Current independent
work and a proven terminal/current-runtime state are reported as such, without
asserting that they prove answer application. See source-proof-map.md for the
precise compatible producer-contract option and adapter-specific limitations.

## Executed proof and antecedents

`operational-focals/qualification.json`, `junit.xml`, `pytest.txt` record the
source-first PR27 dependency environment, literal command, imports, ten input
hashes before/after, exit 0 and drift[]. Result: **48 PASS in 29.11 seconds**:
31 new operational cases and 17 focused legacy cases. Earlier intermediate
results are retained in that report; no prior provider/browser qualification is
inherited.

After that cut, a small final label change applies the same redaction/whitespace
normalization/160-character bound as the connection labels to session-selector
workspace labels. `operational-label-delta/junit.xml` records the exact new
SQLite focal: **1 PASS in 6.91 seconds**, tool fdb04b. The earlier 48-case input
hashes remain antecedent hashes; they are not relabelled as the label-delta cut.
The delta qualification file records current hashes separately. This is a
secret-pattern/bounds proof, not a universal ANSI or telemetry audit.

Meaningful covered cases include complete seven-item requests and sessions pages,
card/principal/version cursor fences, old/current epoch/owner, nonblocking and
parallel work, idle sibling, queue, source/lease expiry, active lease without
opening receipt, agent recipient, no false zero count, native write
refusal/unknown/success distinctions, same-intent canonical decision references,
versioned child-related continuation and productive-table snapshots around HTTP
reads. Pure facts and synthetic historical fixtures are explicitly distinguished
from the admitted inert runtime positive case.

No build, installed-package qualification, global suite, performance p95,
browser/AT, real harness/provider, multi-host, Windows lifecycle or human
acceptance was executed by this milestone. Default rollout remains outside this
qualification. Source/test files are frozen for Root review and wider validation.

## Final currentness delta after readers released

Root explicitly released source readers before this additional change. The
same session batch now joins current execution_agent_revisions and compares the
admitted authorization_revision, configuration_revision and credential_epoch.
The realization's workspace_binding_id must match the session's exact current
workspace binding. Private `authority_current` is distinct from transport/control
currentness: a stale authority scope cannot retain Working, Idle, full blocking
or current native confirmation, even if a prior control boolean was true. Exact
historical context remains inspectable through the canonical resolver.

Four real SQLite negative cases start from a real canonical embedded opening
using the inert Core peer and first establish Idle. Each changes just one proof
field in its own DB (three current revision fields or realization workspace
binding). Each then observes unknown connection/activity, no full block or
confirmation, and native.opens remains one. Four pure prior-state cases cover
Idle, Working, blocked and confirmation with stale authority.

`operational-currentness/qualification.json` and `junit.xml` record **40 PASS in
65.37 seconds**, exit 0, tool 25d761, with all three owner test files repeated
after this semantic delta and introduced lint corrections. This report records
end pins; it does not claim a before/after hash audit for that run. Earlier
48-case and label-delta cuts retain their exact antecedent hashes/results.

The current default checker is `rtk proxy uvx --offline ruff` 0.17.5, whereas the
earlier plain Ruff binary was 0.15.1. New helpers/tests are clean under 0.17.5.
The owner-wide default check retains 34 legacy C408 findings, listed in
`ruff-operational-final.json`; this is not represented as a full default lint
PASS. Root owns the final introduced-versus-baseline differential audit.
`operational-lint-edits.json` records six reviewed dictionary-literal edits with
dictionary-normalized AST equality; no broad legacy cleanup or configuration
change was made. Legacy `project` reduction remains untouched.

HST027 has only prepared scripts/plan under `performance-hst/`; no dataset,
benchmark latency, provider, package execution or performance PASS was created.
Product and tests are again frozen. Root performs the fresh package/build and
wider qualification separately.
