# SAFE-TRACE / AC01 — BASE and service reconciliation

Read-only audit of the fixed R3 plan. No tests, services, providers or credential access. No checkout edit. All references below are retained evidence, not a new campaign.

## Findings

1. SVC-07 has a concrete literal gap: an explicit post-timeout force decision is not exposed by the inspected CLI/request/coordinator. Core containment escalation is a different policy; this audit does not propose bypassing ownership.
2. Several SVC limitations are stale: doctor, enable/disable, recover-start, reviewed environment upgrades and remote bootstrap/renewal already have implementations and scoped evidence.
3. Connect concurrency is supported by compositional seam/process evidence. Occupied port/Ctrl+C and selected startup-failure assertions remain safe qualification gaps, not permission-gated native campaigns.
4. Real-context gaps T09/T14/T15/T18/T19/T21/T29 remain open, as do productive M1/M2 and BASE-06 useful-session timing.

## Task matrix

| ID | Existing | Recommendation | Retained proof | Remaining |
|---|---|---|---|---|
| BASE-01 | VERIFIED | VERIFIED | E22 | Keep historical baseline immutable; no new platform acceptance follows. |
| BASE-02 | VERIFIED | VERIFIED | E22 | This mapping is historical inventory, not blanket proof of every future change. |
| BASE-03 | VERIFIED | VERIFIED | Documentary mapping | No product gap identified by this finite documentation audit; untouched legacy docs are not silently certified. |
| BASE-04 | VERIFIED | VERIFIED | Documentary mapping | No new runtime acceptance asserted. |
| BASE-05 | VERIFIED | VERIFIED | Documentary mapping | Stale SVC limitations/scenario NOT_RUN fields must be reconciled by evidence, not by totals. |
| BASE-06 | IMPLEMENTED | IMPLEMENTED | E01, E02, E15 | Installation-to-first-useful-provider-session/full result/native interaction timing remains NOT_RUN; liveness and synthetic cycles do not replace it. |
| SVC-01 | IN_PROGRESS | IN_PROGRESS | E01, E02, E05, E06, E08, E13 | First supported Windows real user-service acceptance remains open; other platforms need only retain their explicit qualification limits. Keep individual verified subcontracts. |
| SVC-02 | IN_PROGRESS | IN_PROGRESS | E03, E04, E05, E07 | Full occupied-socket startup diagnostic/fixed-endpoint case not located. It is a safe test gap, not Windows installation permission. |
| SVC-03 | IN_PROGRESS | IN_PROGRESS | E01, E02, E07, E08, E16, E17 | Connect-to-facade composition and real process lifecycle are complementary evidence; actual supervised user context/terminal-close work remains distinct. |
| SVC-04 | IN_PROGRESS | IN_PROGRESS | E05, E06, E19, E20 | No direct retained Ctrl+C-connect or startup migration-failure diagnostic assertion located; real provider readiness still open. |
| SVC-05 | IN_PROGRESS | IN_PROGRESS | E08, E09, E13 | Real two-task Windows campaign not executed; login and other OSes have separate unqualified scope. Windows definition validation is not installation. |
| SVC-06 | IN_PROGRESS | IN_PROGRESS | E10, E02 | Actual user-task cwd/PATH/vault/provider context and credential missing/locked behavior remain unqualified. |
| SVC-07 | IN_PROGRESS | IN_PROGRESS | E11, E12, E23 | Literal line325 explicit force decision is not exposed by inspected CLI/request/coordinator; do not equate this with absence of Core containment escalation. External logout/shutdown/context campaign still pending. |
| SVC-08 | IN_PROGRESS | IN_PROGRESS | E07, E11, E18, E21 | Real supervisor crash/backoff/limit and suspend/return context still not qualified; OS loss is not proof of child death. |
| SVC-09 | IN_PROGRESS | IN_PROGRESS | E14, E15 | Actual registered-task update and real historical migration recovery are not proved by disposable same-version environment switching. |
| SVC-10 | IN_PROGRESS | IN_PROGRESS | E01, E02, E06, E09, E14 | Keep verified passive/CLI subcontracts; real terminal-independent productive operation plus SVC07 explicit-force gap remain unclosed. |
| SVC-11 | IN_PROGRESS | IN_PROGRESS | E02, E08, E17, E18 | Loopback synthetic native/provider tests do not prove physical remote host/TLS/service-user vault/productive M1/M2. |
| SVC-12 | IN_PROGRESS | IN_PROGRESS | E01, E02, E15, E18 | Native service tasks/login/context, real useful-work local+remote cycles and first-use timing remain open. Do not call unavailable native authorization a reason to leave pure cases NOT_RUN. |

## Scenario matrix

VERIFIED_SCOPED means the listed finite contract is demonstrated; it is not automatic promotion of every native/platform variant. PARTIAL is an audit label, not a replacement ledger enum. T30 is included because the fixed plan contains it.

| ID | Existing | Recommendation | Evidence | Missing / boundary |
|---|---|---|---|---|
| SVC-T01 | NOT_RUN | VERIFIED_SCOPED | E01, E16 | Composition is supported by the actual connect→ensure_running source seam, injected seam assertion and real facade/process readiness test; it does not qualify a registered task or provider. |
| SVC-T02 | NOT_RUN | VERIFIED_SCOPED | E01, E02, E03, E16 | Canonical service identity depends on configuration/data/user, not project; the shared facade and repeat-start checks compose. Do not require one monolithic campaign merely because assertions are separate. |
| SVC-T03 | IN_PROGRESS | VERIFIED_SCOPED | E01, E02, E03, E16 | The real concurrent start and connect→same-facade assertion compose; no extra protocol/provider effects are inferred. |
| SVC-T04 | NOT_RUN | VERIFIED_SCOPED | E03 | Windows held-lock contract verified; do not claim all filesystems/OSes. |
| SVC-T05 | IN_PROGRESS | VERIFIED_SCOPED | E04 | Stale/unknown/reused PID does not prove death and cannot steal live OS ownership; no historical-PID killing. |
| SVC-T06 | NOT_RUN | PARTIAL | E05 | A real occupied TCP socket during start and no endpoint/DB fallback assertion not located. Safe isolated test gap, not authorization. |
| SVC-T07 | IN_PROGRESS | VERIFIED_SCOPED | E08 | Actual Task Scheduler start remains the explicit native campaign; scope label must retain injected adapter. |
| SVC-T08 | IN_PROGRESS | VERIFIED_SCOPED | E06, E17 | Synthetic transport/topology scope; real external network availability is not claimed. |
| SVC-T09 | NOT_RUN | PARTIAL | E01, E02 | Literal terminal/dashboard closure with admitted work and maintained native ownership remains real campaign. |
| SVC-T10 | IN_PROGRESS | VERIFIED_SCOPED | E06 | Explicit doctor probes are separate opt-in checks. |
| SVC-T11 | NOT_RUN | VERIFIED_SCOPED | E05 | Wrong instance/generation/version is refused despite HTTP reachability; live unreachable owner is not declared stopped. |
| SVC-T12 | NOT_RUN | PARTIAL | E19, E05 | Startup invalid-config/migration diagnostic cases not mapped; no blanket permission barrier. |
| SVC-T13 | IN_PROGRESS | PARTIAL | E20, E12 | Retained Ctrl+C during actual connect not located. Log-follow Ctrl+C is not a substitute. |
| SVC-T14 | NOT_RUN | PARTIAL | E10, E01, E02 | Actual registered service with reduced/different PATH/cwd and correct project still needs service context campaign. |
| SVC-T15 | NOT_RUN | PARTIAL | E06, E10 | Real terminal-only credential and locked OS vault under service user is unexecuted. |
| SVC-T16 | IN_PROGRESS | VERIFIED_SCOPED | E02, E06, E10 | Finite synthetic sentinel/definition coverage, not proof of arbitrary unknown secret formats. |
| SVC-T17 | IN_PROGRESS | VERIFIED_SCOPED | E08, E09, E13 | Scheduler effects injected; real native integration remains separately pending. |
| SVC-T18 | NOT_RUN | NOT_RUN_REAL | E08, E09 | Actual OS logon startup must be observed; no boot-without-login claim. |
| SVC-T19 | NOT_RUN | PARTIAL | E08, E11 | Real supervised crash/backoff/limit exhaustion and actionable persistent failure not executed. |
| SVC-T20 | NOT_RUN | VERIFIED_SCOPED | E01, E02, E11 | Do not call injected OS suppression actual scheduler crash qualification. |
| SVC-T21 | NOT_RUN | PARTIAL | E11, E12, E23 | External logout/shutdown bounded persistence unqualified; explicit-force UI path is separate SVC07 product gap. |
| SVC-T22 | NOT_RUN | PARTIAL | E12, E21 | Real service restart with surviving native child/uncertain operation remains unexecuted; no new general product defect established. |
| SVC-T23 | NOT_RUN | PARTIAL | E01, E02, E15, E18, E21 | Available proofs compose restart persistence with canonical grant authority. If wiring needs an additional assertion, it is a safe disposable restart test; neither registered OS service nor provider is required by T23. |
| SVC-T24 | NOT_RUN | PARTIAL | E18 | Dedicated continuity/remote suite assertions still need read-only mapping; renewal alone is not substituted. This is safe evidence reconciliation, not a requirement for physical hosts. |
| SVC-T25 | IN_PROGRESS | VERIFIED_SCOPED | E05, E14 | Metadata seam version test; protocol-only RG07 old/new client/server campaign does not itself qualify old daemon supervision. |
| SVC-T26 | IN_PROGRESS | VERIFIED_SCOPED | E14, E15 | No historical schema binary downgrade recovery or real task upgrade claimed. |
| SVC-T27 | NOT_RUN | PARTIAL | E13 | Actual native removal followed by same preserved data in foreground remains native campaign scope. |
| SVC-T28 | NOT_RUN | PARTIAL | E10 | Container/external-supervisor real execution not located; POSIX templates explicitly unqualified. |
| SVC-T29 | NOT_RUN | NOT_RUN_REAL | None | Separate actual-context campaigns, neither prepared finite install lifecycle nor synthetic runtime proves them. |
| SVC-T30 | IN_PROGRESS | VERIFIED_SCOPED | E01, E02, E15 | Does not promote real registered user-service/login/provider context. Included because literal plan has T30 in addition to parent-requested T01..29. |

The full JSON stores literal plan text, current source symbols/lines/SHA-256, exact retained passing testcase identities and report paths. Historical reports are not summed, and current source hashes do not retrospectively attest historical fixture bytes. The audit recommendations do not edit tasks, scenarios, gates or authorization.
