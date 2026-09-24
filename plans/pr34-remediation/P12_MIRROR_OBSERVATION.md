# P12 — nonexecuting mirror observation

Parent `b263de92223cf839a1e14efac481c5b071e15f75` plus exact generation hashes and commands in
[evidence index](evidence/p12-mirror-observation-index.json). Original missing-route RED was executed
against a6a18b4 and committed in b263de9. Schema063 is additive; surface57/identity25 remain unchanged.
The optional adapter input marker `context_observation_contract=1` versions the new port separately.

## Behavior and integration

The approved same-agent/workspace observer receives an information envelope for a canonical conversation
that selects an exclusive executor. It requests no response and carries no execution bootstrap or handoff
grant. RuntimeDeliveryPlanner records subordinate observation attempts in the original message/delivery/
outbox transaction. SqliteRuntimeObservationRepo never changes inbox consumption, claims or execution
budgets. runtime_context_observations references the original outbox operation, preserving its unique
executor-per-delivery constraint and avoiding a second logical work queue.

ContextObservationConnector.observe_context is optional and distinct from send/send_turn. The trusted
registry marker, descriptor capability, compatibility probe, implemented method and approved profile
must agree. QualifiedConnector intersects these facts; missing method/probe remains false. Supervisor
tracks active observation calls for shutdown and checks effective support again before IO. No native
adapter was modified to claim unsupported context injection; all four retain their existing capabilities.

RuntimeCommandDispatcher is reused with one bounded observation worker under the existing owner,
wake generation and shutdown coordination. Owner/attempt CAS protects observations; possible write or
timeout remains OUTCOME_UNKNOWN and never retries automatically. A timed-out call occupies its slot
until it actually returns. Pending observations of a closed session are cancelled on the owner scan;
explicitly reopening permits only newly admitted contexts in the new session. It never transfers the old
uncertain attempt. The existing application clock timestamps this transition.

RuntimeObservationService revalidates canonical source authority, credential, audience/policy, endpoint,
profile, current session and owner before dispatch. Count/byte bounds apply per agent/workspace/store.
Transport IO occurs outside writer UoWs. Public harness_get on the original executor operation exposes
context_observations only for endpoints the caller may read; it distinguishes persisted attempt durability,
no observed external acceptance, no result and no execution authority. No new tool or raw passthrough exists.

## Executed evidence

- Original RED: Windows46168,1 FAIL33.96s. Approved observer opened successfully; the exclusive executor
  received one turn, but no context reached the observer. No import/setup failure.
- Initial implementation: Windows31539,1 PASS30.60s.
- Expanded generation: Windows70251,7 PASS60.02s; Linux44733,6 PASS1 FAIL129.89s. Linux retained an
  OperationalError in the public read. Review found authorization audit writing inside a read snapshot;
  the nested metadata check now uses audit=False, while original operation access remains audited.
- Read-only guard generation: Windows45707,7 PASS41.29s; Linux60918,7 PASS41.59s. The positive test sets
  PRAGMA query_only=ON for read UoWs, making accidental read-to-write promotion fail deterministically.
- Broader observer generation: Windows24961,12 PASS54.45s; Linux16021,12 PASS60.14s.
- Existing-path regression: Windows78039,78 PASS1 POSIX SKIP310.44s; Linux51172,79 PASS350.97s, one existing
  Starlette deprecation warning each. Includes16 unsafe mirror create/update REST/MCP cases for the four
  native adapters, plus commands, shutdown, capability admission, discovery, actual serve signal drain,
  migrations, import boundary and the original fifth-adapter extension. These hashes precede the final
  closed-session adjustment; they are not relabeled as a run of later source.
- Closed-session RED: Windows59781,1 FAIL19.02s; an unsent observation remained PENDING after close.
- Final observer generation: Windows34030,13 PASS131.89s; Linux35170,13 PASS268.83s. Both terminal exit0.
  Adds explicit close/reopen without replay and verifies prior unknown state remains unknown.

Final13 cases cover the real HTTP/MCP route, one executor reservation, current authorization changes,
read grant separation/revocation, absent method/probe, atomic rollback after actual observation INSERT,
uncertain transport with stale-epoch CAS rejection, bounded physical worker occupancy and close/reopen.
The requirement index joins these13 nodes with the16 native-negative nodes on each platform. Intermediate
failures and overlapping successful generations are retained separately, never summed into a fresh total.

Exact pytest commands are in every manifest. Ruff on all changed Python files and git diff --check PASS.
Required isolated `rtk proxy .venv/Scripts/python.exe scripts/live_client.py` passed before and after the
final production adjustment (final handle9694 exit0, LIVE E2E RESULT:PASS). Raw output containing ephemeral
fixture credentials was not committed. Raw XML remains under .git/pr34-evidence.

## Scope and next dependency

T-CONS-07 scoped PASS. This proves the optional processless context adapter through actual production
composition, not native-provider observation. Only ready, verified observers of the selected conversational
executor route are eligible; this does not claim offline catch-up, handoff observation, independent pull
mirroring, native ACK/deduplication or general delivery guarantees for unsupported adapters. The observer
must be explicitly opened or configured for boot. The four native adapters remain ineligible for mirror-only.

Original matrix125 PASS/4 NOT_RUN; final gate NOT PASSED. Remaining implementation: authenticated external
attach work T-WORK-12. Native E2E01/02 retain authorization/environment limits. Final report E2E07,
immutable-source full suites, final finding/release audit and local reinstall0.2.0 remain pending.
