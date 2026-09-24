# Confirmed observations at P00

Source SHA d7d87d0; regression log `evidence/p00-red.log`. FAIL means the desired
invariant failed on the baseline. No item below is claimed fixed yet.

| Finding | Observed mechanism and evidence | Remediation |
|---|---|---|
| F01 | `test_profile_is_unchanged_by_open_close`: capabilities/metadata replaced by `HarnessSupervisor.open` → AgentRepo.upsert. Unknown identity also created. | P01–03 |
| F02 | Authenticated real HTTP MCP caller controls/reads foreign sessions and opens arbitrary agent; six parameterized negative cases return success. Additional keyed-loopback REST bypass reproduced: middleware ignores an explicit key. | P01/P04 |
| F03 | `test_one_delivery_does_not_execute_on_two_sessions`: two native send commands for one recipient delivery. Each session subscribes to agent notifier. | P05 |
| F04 | `test_committed_delivery_survives_lost_notification`: committed inbox has no durable transport intent. Callback dropped after commit leaves no recovery state. | P05–06 |
| F05 | `test_terminal_storage_failure_is_not_silently_accepted`: terminal append failure swallowed after publication; no durable journal. | P08 |
| F06 | `test_forward_preserves_sender_subject_and_message_identity`: wire is only text/content body; sender, subject and message ID absent. | P02/P07 |
| F07 | Foreign authenticated caller's harness_send succeeds and issues send_turn without canonical handoff/claim or administrative authority (AUTH send case). Supervisor only checks technical capability. HandoffService is not used by that path. | P04/P09 |
| F08 | `test_expired_relay_does_not_mint_new_root`: expired root returns new chain and depth 1. Source tracked on session, not operation. | P10 |
| F09 | `test_additional_adapter_is_not_rejected_by_domain_product_enum`: domain rejects additional adapter ID; factories are a fixed product map. | P02 |
| F10 | `test_unconfigured_surface_does_not_publish_harness_tools`: all eight tools advertised by default. Registration eagerly builds supervisor. Serve has cleanup/watchdog but no declared-boot invocation. | P01/P06/P11 |
| F11 | Baseline fails Windows collection and six process-reaping tests. Bounded call creates daemon thread per call; close timeout does not cancel it. Further lifecycle fault cases pending. | P07/P12 |
| F12 | Open writes Agent and harness_sessions, not canonical sessions/workspace presence. Existing target tests manually seed presence; full routing/presence campaign pending. | P03/P05 |
| F13 | `test_backend_diagnostics_do_not_echo_credentials`: fixture token echoed verbatim. Codex factory selects hardcoded never/danger-full-access, no approved profile. | P03/P04/P07 |
| F14 | `test_replay_keeps_event_id_and_sequence`: DB sequence/event ID dropped by event reconstruction/serialization. Guide contradicts later relay implementation. | P08/P11 |

Historical fixes are retained: target-grammar forwarding exists; attach events
now broadcast snapshots rather than destructive shared deque; orphan watchdog
exists. Their existence does not establish durability, Windows lifecycle, or
the new acceptance gates. We do not reimplement the superseded blanket
harness-to-harness ban.

## F13 additional reproduced path at e388227

The completed full Windows suite was green, but an independent approved-profile
audit showed that an opaque secret_refs value echoed by an owned protocol peer
was persisted in journal/result/replay. Known credential-pattern redaction alone
was insufficient. Four subsequent behavioral regressions covered complete/split/
one-character output and a startup error. See P03_BACKEND_SECRET_REDACTION.md and
evidence/p12-backend-secret-audit.json for the source, isolated fixture and narrow
correction. No personal/provider credential was used; no historical capture was
replayed. The final gate remains separate from these selected checks.

## P09 authenticated handoff boundary (F02/F07, parent c67e7dc)

Confirmed through actual HTTP MCP: creator API key with claimant agent_id could complete claimed work. Fixed shared service actor/binding validation for all handoff verbs; HITL preserves original creator binding. See P09_AUTHENTICATED_HANDOFF.md and test_runtime_handoff_epochs.py. Windows 212 PASS; Linux 25 PASS. Scoped runtime bootstrap/dispatch remains pending.

## P10 additional finding F15 — target discriminator normalization

Confirmed while adding explicit notification routing on parent 6540cd7:
`message_action_for` compared the raw strategy case-sensitively although canonical
routing accepts `BROADCAST`. The behavioral test published to two recipients despite
the originating actor's broadcast deny. Shared governance now uses
`domain.targets.target_strategy`; lowercase/uppercase negatives both pass. See
P10_NOTIFICATION_TARGETS.md for RED, correction and final Windows/Linux results.


## F05/F04 additional admission gap at 3e87578

Known journal quota/fsync failure stopped native dispatch but did not stop new
executable admission: authenticated REST send returned PENDING/durable=true and
MCP message creation committed a transport intent after the capture failure.
Four clean behavioral RED cases reproduced this at 3e87578 (not import failures).
Schema062 extends the existing runtime_writer_contract with an owner-fenced
capture availability bit and database admission guards; updated repositories
share the same transactional check, including independent stdio writers.
See P12_CAPTURE_ADMISSION.md for scoped results, failures and recovery limits.


## F03/F09 — positive nonexecuting observer route

At a6a18b4 an approved, ready context-only fixture endpoint received no observation while the same
canonical delivery reached its exclusive executor. The committed b263de9 reproducer failed on absent
context, not imports or missing configuration. Optional context observation v1 is a new implementation
decision satisfying the specified mirror-only invariant, not an invented native capability. The four
built-in adapters still lack verified context-without-execution and remain ineligible for mirror-only.
See P12_MIRROR_OBSERVATION.md and its generation-specific evidence. Implementation preserves one inbox
reservation and uses subordinate transport attempts with no ACK, result or work authority. During this
unit, a public-read OperationalError and a closed-session pending observation were also retained and
corrected; their failed runs are not counted as acceptance passes.


## External attach work compatibility, corrected before publication

T-WORK-12/F02/F07/F14: the pre-fence working integration admitted a legacy writer-v1 claimant/epoch
handoff transition without the new external proof. This development-generation defect was reproduced
by test_runtime_external_writer_fence.py (1 clean FAIL) and fixed by migration064's narrow triggers and
ConnectionFactory's external-work capability marker. Final three legacy-writer destinations/ACK checks
and authenticated current completion pass on Windows/Linux. Parent49ebd0e still refused managed attach;
this is not claimed as a reproduced vulnerability of that commit or the original PR34. Exact generation
hashes and the integrated external work gate: P12_ATTACH_WORK_INTEGRATION.md.

### External work development-generation retention/recovery corrections

Before publishing the external work integration, real tests reproduced retention FK failure for a referenced closed session and an invalid permission refusal when rejecting an explicitly recovered OPEN offer. IdentityRepo count/prune now retain referenced audit sessions while deleting unrelated expired sessions. HandoffService scopes the external-return guard to the current CLAIMED handoff. Both REDs and final Windows81 PASS1 SKIP/Linux82 PASS operational evidence are retained in P12_ATTACH_WORK_INTEGRATION.md and its manifests. These are unpublished working-generation defects, not findings against the earlier PR or parent49ebd0e.
