# M3k real UI: owner replacement and interrupted caller

Date: 2026-10-17. Initial Nexus M3k wheel SHA-256
`bdeb038d0c1a4d8e7ed167b9fc07faf91875871113cd3c53fdaba119d0cab876`.
The global generation 73 on port 8202 was not stopped, modified or faulted.

## Disposable real-provider observation

`tools/runtime_ui_fault_fixture.py` started the installed wheel with a new
home and empty workspace below `build/runtime-m3k-real-ui`, loopback port 8204.
Server PID 4032, launcher 44000. The wrapper adds no HTTP fault endpoint and
does not replace native harnesses. A private request file triggers one normal
dispatch-owner containment; another requests retained graceful shutdown.

Through the real Nexus UI, a Worker agent `m3k-pi` was created, its local Pi
0.87.1 installation selected and verified, and its connection saved. The new
workspace appeared immediately in Meta-harness. A baseline message returned
`M3K_BASELINE_OK` with 1/1 acknowledgement. Session:
`ses_ca7f1843ec57d73a38f7f1163acebb0a`.

A second message asked the real harness to execute a harmless Python sleep
once. The terminal showed a turn starting at 08:44:14 UTC and a bash action at
08:44:19. After injection, the committed tool output showed `python: command
not found` (exit 127). This is therefore **not proof of containment of a live
sleep subprocess**. It does exercise an admitted real turn without a final
response; the replacement run must use `sleep` in Pi's shell instead.

The private fault request was observed at 08:44:40.173 UTC. Owner generation 2
drained at 08:44:41.691. Generation 3 appeared at 08:44:41.904 and had an active
dispatch pump with no blocked agents at 08:44:42.935. HTTP stayed in PID 4032.
Five connection/profile/workspace table hashes stayed equal to the pre-fault
snapshot. No manual Recover, reconfiguration or browser reload was used.

The original session became CLOSED/CLOSED. Its submitted turn
`op_7e76cad098908c5bd9f3499f2f772091` retained its honest SUBMITTED receipt;
resource release does not establish native success, cancellation or absence of
effects. The Meta-harness showed 0/1 ACK and no caller outcome. This is a real
acceptance failure, not a successful end-to-end M3k qualification.

A new message at 08:45:12 was admitted to a different session,
`ses_cd7d96715dec8ac808bc69a351965800`. Its operation
`op_73aba5ceb6ace62ad40430e766cf5150` reached SUCCEEDED. After two transient DOM
observation timeouts, a screenshot confirmed `M3K_AFTER_RECOVERY_OK` with 1/1
acknowledgement in the same Meta-harness tab, without reloading. Evidence is retained in the private test home,
`evidence.jsonl`, and `observations.jsonl`.

The disposable instance then drained with no remaining resources/error codes
at 08:53:42.940 UTC and finished its lifespan at 08:53:43.544. Its process and
port listener were absent at the subsequent OS check. No forced stop was used.

## Caller-notification correction

A separate server notification now derives solely from the proven release and
original admitted conversation. It records one durable private reply to the
original caller, with the original message as parent. It explicitly states that
the session ended without a final response, actions may have taken effect, and
the request will not be replayed automatically. It never creates a fake native
receipt/result, acknowledges the original message, completes a handoff or starts
a runtime relay. One-shot calls retain their existing failure-notification path.

Migration 146 separates notification deduplication from resource evidence. It
marks pre-upgrade releases as historical without sending old conversations.
Message, inbox delivery, notification event and deduplication marker commit in
one transaction. A failed append is retried with the same deterministic identity.

The sections below record final source, installed and repeat real UI evidence
for this correction. Global rollout, full UI-A and the remaining restructuring
plan are not complete.

Initial source qualification passed four cases in 142.87 seconds (all three
adapter paths and atomic notification retry). The subsequently expanded source
campaign included additional sender-mismatch and upgrade checks, independent
recovery and one-shot regressions. The first correction artifact was installed
only in the disposable environment and subsequently superseded by the final
pending-index revision described below. It was not accepted for rollout.

Review found that the first notification query scans historical delivery rows.
A standalone SQLite instruction-count probe using the actual query recorded
31,226 / 301,226 / 3,001,226 VM instructions for 1k / 10k / 100k historical
releases with no pending notification. The query plan scans `delivery_outbox`
and sorts. This probe uses a minimal schema, not a production timing benchmark.
The query was replaced with PENDING notification records enqueued in the release
transaction and a partial pending index. The same probe now reports 1,374 VM
instructions at all three history sizes, scans only the pending index and seeks
the related rows by key, without sorting. Deduplication stays separate from
release proofs and preserves the historical migration rule. The expanded source
campaign started before this final revision and is preliminary only; its inputs
changed during execution and it is not final qualification. A new focused source
campaign and rebuilt candidate cover the final revision; installed testing must
verify frozen inputs before acceptance. The intermediate artifact is superseded.

## Repeat real UI with final notification candidate

Final wheel SHA-256:
`dc0d8130ec7ac33fb368e0c035c4a85dc1cef4d519c2e45b44a524348cd7c5db`.
All 545 installed files match the wheel and 538 non-generated package files
match source. Dependencies are compatible. The five final focused source cases
passed in 87.23 seconds. The earlier expanded run returned 40 passes, but is
not accepted as final-revision qualification because its inputs changed while
running. The final frozen-input installed campaign completed with 57 passes and two rollback-test races; the focused rerun and exact scope are recorded below.

The fixture resumed its previously drained disposable home with fresh private
control files. Server PID 38332, generation 4. Existing agent/configuration and
historical messages remained available. Migration 146 marked the old incomplete
call HISTORICAL without sending a retrospective notification.

A new message sent through Meta-harness at 09:11:51 UTC asked Pi to run `sleep
45` once. Session `ses_76436f291d851418c561f3c9c9f79fc0`, turn
`op_ddc4e5abcbbb28295cf86d581359a8f5`. The terminal showed the bash call running,
without final output, before containment. The fault was applied at 09:13:40.115.
Generation 4 drained at 09:13:41.683 and generation 5 had a dispatch pump and no
blocked agent at 09:13:43.537, in the same HTTP PID. No reload or manual recovery
was used.

Meta-harness displayed one `Nexus runtime interrupted` reply containing
`RUNTIME_SESSION_ENDED`, explicit possible-effect uncertainty and no automatic
replay. Its parent is `msg_775b4851684b4dc5a9760490a512cbbe`, its only recipient
is `operator`, and its domain operation is `op_211ea3bf49464cc78c97859b031dc907`.
There is exactly one PUBLISHED release notification. The original turn receipt
remains SUBMITTED and the original message has 0/1 ACK, rather than fabricated
success. All observed dispatch attempts remain 1; no native result was invented
for the interrupted turn.

A new UI message at 09:14:17 opened session
`ses_800b1adfb7c8d73cfff368a6c93a55d0`. Its turn
`op_c18ff61a0bbbdbca98871f75e5e686e8` returned `M3K_FINAL_RECOVERED_OK`, visible in
Meta-harness with 1/1 ACK. Agents displayed Local Online. All five configuration
table hashes still matched the original pre-fault baseline; foreign-key checks
were clean. Screenshots were captured in browser tool output, not saved as
local image artifacts.

The final disposable run drained with no resources/error codes at 09:16:08.655,
finished its lifespan at 09:16:09.772, and its process/port listener were absent
afterwards. Production generation 73 remained untouched throughout. This is
real Pi qualification of this containment/caller-notification path; it does not
replace the outstanding full UI-A/three-provider/load/Connector gates.

## Final installed acceptance

The 59-case campaign finished with 57 passes and two failures. Both failures
were exact message-table rollback comparisons racing the newly asynchronous
interruption notice after closing unfinished work. No production code changed:
the tests now await that real notice before taking their baseline, retaining
the original full-row equality, generation, foreign-key and immutability checks.
All eight reset cases then passed against the identical wheel and dependencies.
Both campaigns had frozen inputs; the only input difference between campaigns
was `tests/execution_r4/test_reset_connections.py`. This qualifies 59 distinct
cases through the combined evidence; it is not a claim of one green 59-case run.
See `m3k-notifications-results.json`. No global rollout occurred.

The same installed candidate also passed idle and active reset through the real
Pi UI, preserving configuration and serving new work; see `m3k-reset-ui.md`.
