# PR-03 — canonical terminal work and native decisions

Windows 11 `10.0.26300`, Python 3.13.1; Nexus `0.3.3` on
`feature/v0.3.3`. Connector `0.0.12` and Core `0.0.14` are unchanged in this
increment. All three `origin/main` references were fetched and confirmed
contained in the feature branches. R3, PR-03 and M1 remain incomplete.

Interactive `connect` now enters the project work prompt after approved setup
or validated reuse. `--plan`, `--json` and `--no-chat` do not enter it. No project
request is submitted until the user enters one. `work` offers send, conversation
continuation, status/watch, session/event inspection, native question/permission
review and decisions, submission recovery, explicit interrupt and explicit close.

The application facade calls the existing operator HTTP handlers for intents,
admission, sessions, events, approvals, decisions and results. It does not write
database tables or introduce a second executor/authority/conversation store.
Scope checks include Server, executor, binding, project agent, workspace and
session. The project/harness/home connection is revalidated before work.
Local files retain bounded references, request context without text, hashes and
recovery checkpoints. Prompts, answers, events and results are not copied there.

Each submission records its stable ID before resolution and admission. A lost
reply is recovered through the same canonical intent/operation. Missing
resolution requires exact explicit re-entry; a changed request cannot replace
an uncertain one. Work and interruption/closure have separate checkpoint slots.
A retained existing session is reused only while the canonical view allows it;
starting another session requires an explicit user request.

An additive `initial_turn_operation_id` on the canonical intent read correlates
the prompt belonging to that request. It is derived from the existing stored
initial-turn resolution, checked for scope/action/hash, and does not change
admission or storage. Reusing a runtime opening can have children from multiple
requests; listing all those children as the current answer was incorrect. The
facade now follows only the current request's child and verifies session scope.
An older response without that correlation remains explicitly uncertain and
does not trigger a replacement submission.

Canonical output and receipt stage distinguish admission, execution, completion,
pending input, refusal and uncertainty. Event pages retain cursor/gap/truncation
information. Observation uses current reads, including work already completed
before watching; timeout and Ctrl+C stop only the observer. EOF also leaves
pending questions intact in chat and standalone watch/answer. Session closure
and interruption use their explicit canonical controls. A profile lock prevents
two terminal writers from replacing each other's checkpoints.

Native decisions use the actual actor/recipient, complete approval key, expected
revision, request hash, CAS, expiry and explicit answer. The forms cover Codex
questions, Claude AskUserQuestion, bounded MCP elicitation and Pi
input/select/confirm/editor. Their answers are tested against Core's existing
native response validator. No permission, option or boolean is preselected;
control characters are escaped for human display. Noninteractive decisions
require the displayed review hash and optionally a bounded UTF-8 JSON answer.

Lost decision replies recover the recorded decision without another POST or
private-answer replay. A confirmed validation refusal permits a corrected
answer; uncertain submissions retain their original answer digest and ID.
Recorded decisions and actual native delivery are shown separately. The
existing `feature_hitl=false` default correctly refuses native delivery even
after a canonical decision is recorded. Tests explicitly enable the feature for
positive cases and retain a disabled-policy refusal case; the product gate was
not weakened or silently enabled.

## Validation and package provenance

Source reports: **29 focused tests**, **44 regression tests** and **2 observer
exit tests** passed, without skips. The first focused report predates the added
full interactive cycle and final EOF cases. The full interactive cycle also
passed separately during development; the final installed campaign includes it.

The broad installed run passed **99 of 102 cases**. Three cases failed because
the external test copy omitted `plans/contratos/http-target.schema.json`; all
three reached their schema-fixture read. The original XML is retained. The test
preparation was corrected to copy the contracts, without changing the schema or
weakening an assertion. The final campaign passed **35 tests**, without skips,
covering all terminal-work/forms/transport cases plus those three schema cases
on the rebuilt wheel after the EOF fix. Its outcome is recorded in
`pr03-terminal-work-final.xml` and the ledgers.
Campaigns overlap and are not summed as a unique-test count.

Reports:

- `pr03-terminal-work-source.xml`
- `pr03-terminal-work-regression.xml`
- `pr03-terminal-work-observer-exit.xml`
- `pr03-terminal-work-installed.xml` (99 passes, three missing-fixture failures)
- `pr03-terminal-work-final.xml` (final artifact and corrected fixtures)

Both installed runs use copied tests with `python -I -m pytest` outside the
checkouts and assert Nexus/Connector/Core module origins in the validation venv:
`C:\Users\jpamb\AppData\Local\Temp\r3-terminal-work-mqiy1eq4\validation`.
The initial package hashes are in `pr03-terminal-work-initial-wheels.json`;
final hashes are in `pr03-terminal-work-wheels.json`. All 423 Nexus, 114 Connector
and 130 Core Python payloads match source bytes. The final Nexus SHA-256 is
`253ef11022594a6848d4bd793e0b3cd41477cefe91d913f50272613ff80b3b07`.
Its only production change from the broad-run artifact is handling EOF at the
work entry point. The unchanged pinned Connector/Core wheels are installed in
the same environment. Candidate wheels were built with `uv build --wheel`;
Nexus uses its `serve-lite` extra.

Broad installed targets: `test_terminal_work`, `test_terminal_connect`,
`test_terminal_identity`, `test_initial_turns`, `test_operator_runtime`,
`test_native_decisions` under `tests/execution_r4`, plus
`test_terminal_native_input`, `test_terminal_http`, `test_terminal_connect_process`
and `execution_r4/test_cli_http_only`. Final targets are the terminal work,
native input and transport suites, the actor-namespace/schema test and both
canonical decision CAS/replay parameterizations. JUnit is written with
`--junitxml`; all runs use `-q --tb=short`.

The terminal integration uses real HTTP handlers, authentication, SQLite
transactions, Core lifecycle, outbox/dispatch and canonical receipts/events.
The native peer and its model output/questions are synthetic. Tests cover lost
resolution/admission/decision replies, exact re-entry, scope drift, same-ID
conflict, two requests sharing one opening, conversation continuation, explicit
close, private-data exclusion from checkpoints, native policy refusal, terminal
EOF/Ctrl+C and a complete scripted request/question/answer/result/reopen cycle.

The existing real-process regression starts/reuses a disposable Server through
the CLI, reaches HTTP and ends in `DRAINED` after explicit stop. Passive work on
an absent home does not bootstrap it. The transport test accepts an escaped
1 MiB canonical output under its explicit 8 MiB wire bound. No personal service,
real provider, credential or native scheduler task is used.

Development fixes corrected a CONFIRMED/COMMITTED assertion, synthetic native
form fields and explicit native-policy test setup. Review found and fixed EOF
escaping standalone question handling. Ruff `--select E9,F` passes for changed
Python files; the broader inherited style rules still report suggestions
(imports, dict literals and simplifications), including existing code. This is
not a claim that the full style configuration passes. Whitespace and the fixed
plan ledger coverage are checked separately.

## Remaining fixed-plan requirements

DX-09/10/11 are advanced only for native operations needed by M1. Generic
message/handoff creation deduplication, coordinated wait and all corresponding
scenario acceptance remain unfinished. There is no new coordination journal.

The default local route still needs reviewed activation of native decisions,
terminal renewal of expired execution grants, start-at-login in the same
onboarding review, remote operator authentication/Connector integration,
participant init, optional preset evolution and dashboard introduction. Real
harness context, native form behavior, coordination and productive local/remote
campaigns remain unqualified. No real Server restart or provider-session restore
is established by reopening these test CLI objects.

The original isolated Windows native-service campaign still awaits its already
requested authorization. Its candidate/plan was not replaced and no task was
registered. Synthetic terminal results do not satisfy DX-T39/40 or complete M1.
