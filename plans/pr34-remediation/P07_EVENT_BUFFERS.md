# P07/P08 — bounded native event history and subscribers

Parent `2b6b3a9`, branch `feature/v0.2.0`. Partial checkpoint; final gate NOT PASSED.

All four adapters now use `NativeEventHistory`: up to 2048 events and four MiB
of serialized event bytes per native connection, with a rolling transient replay
window. Serialized byte accounting is not an exact Python RSS promise. Expired
replay raises `NativeReplayExpired`; a caller never receives a truncated history
silently advertised as complete. Codex filters replay by session, so expiration
in one thread does not itself prevent a new thread's subscription. Expired-session
tracking is bounded too; after its 64-session tracking limit, expiration becomes
conservative for the connection.

Each managed adapter admits at most 16 native subscribers, each with at most
128 queued events and two MiB of serialized event bytes. Append and nonblocking
fanout share an ordering lock. Overflow latches a gap, stops the actual owned
process, drains the retained queue prefix, then raises `NativeEventOverflow`.
The supervisor journals `outcome_unknown` with `failure_type`, quarantines the
binding and removes the subscription. In a shared native process, a transport
fault can stop the entire owned connection. No process lookup/kill by generic
name or arbitrary external PID is introduced. Attach only retains bounded local
diagnostics and never invokes this process-stop helper.

An event rejected by a full queue is **not claimed durable**. Retained terminals
drain before the explicit gap; the gap is not a turn-completion or retry grant.
Healthy streaming consumers keep receiving events when old transient history
expires. Historical API replay remains the authenticated canonical journal/SQLite
path, not a second native subscription.

Interface version: built-in `event_stream_contract_version = 2`, propagated by
EnvelopeConnector; legacy trusted connectors default to v1. The unchanged v1
delivery envelope, v1 registry contract and v1 durable journal format are separate
contracts. Updated HarnessConnector port documentation and CONTRACT_MAP.md explain
the bounded native replay behavior. No migration.

Reproduction:

`.venv/Scripts/python.exe -m pytest tests/test_runtime_event_buffers.py -q --tb=short`

7 behavioral FAIL before correction (`evidence/p07-event-buffers-red.log`): all
four histories exceeded the byte bound and all three managed subscriber queues
grew beyond the count bound. An initial fixture used invalid `text_delta`; it
was corrected to canonical `output_delta` before recording these seven behavioral
failures. Post-fix initial 7 PASS (`p07-event-buffers-progress.log`); expanded real
REST/pipe-peer overflow check 8 PASS (`p07-event-buffers-expanded.log`).

Expanded integration command:

`.venv/Scripts/python.exe -m pytest tests/test_runtime_event_buffers.py tests/test_runtime_contracts.py tests/test_runtime_shared_connection.py tests/test_runtime_event_journal.py -q --tb=short`

45 PASS in 28.92s (`evidence/p07-event-buffers-integrated.log`). Includes count and
byte pressure, subscriber limit/release, scoped expired replay, retained terminal
drain and a production REST/native-transport/journal test with deliberately slow
capture. That test observes process reaping, explicit durable uncertainty and
endpoint quarantine, with no synthetic completion. Pure attach callback tests
do not count as a real attach session or a POSIX transport test.

Broader command, all old native flags explicitly 0 and native campaign empty:

`.venv/Scripts/python.exe -m pytest tests/test_runtime_event_buffers.py tests/test_runtime_protocol_limits.py tests/test_harness_codex_connector.py tests/test_harness_pi_connector.py tests/test_harness_claude_code_connector.py tests/test_runtime_process_ownership.py tests/test_runtime_shared_connection.py tests/test_runtime_event_journal.py tests/test_pr34_remediation.py -q -k 'not expired_relay_does_not_mint_new_root' --tb=short`

169 PASS, 9 skipped, 1 P10 regression deselected, 1 existing injected Pi callback
warning in 176.85s (`evidence/p07-event-buffers-gate.log`). Ruff and diff checks PASS.

Real isolated campaigns, same explicitly configured executable/login-source paths
from NATIVE_CAMPAIGN.md, fresh temporary project/config/store for every test:

- Codex: `pytest tests/test_runtime_native_campaign.py -q -k codex --tb=short`:
  **2 PASS, 1 deselected, 15.51s**; `evidence/p07-native-codex-buffer-gate.log`.
  Canonical two turns and active-close interruption; observed gpt-6-astra/openai.
- Claude stream: `pytest tests/test_runtime_native_campaign.py -q -k claude_code --tb=short`:
  **1 PASS, 2 deselected, 10.55s**; `evidence/p07-native-claude-buffer-gate.log`.
  Canonical two turns, observed claude-opus-5 / claude-opus-5[1m].

All three temporary login copies independently checked absent. Processes reaped
and final lifecycle observed `stopped`. Sanitized read-only observations:
`evidence/p07-native-buffer-observations.json`. Pi/attach native remain NOT_RUN.
These are fresh execution counts, not copied from the original PR.

Changed symbols: event_buffers classes/helpers; four adapters' event history,
subscription and emission paths; EnvelopeConnector version forwarding;
HarnessSupervisor._capture_lifecycle/_finish_reap failure attribution; port docs.

Remaining: Codex unmapped early-event cache and lifetime thread bookkeeping,
Claude pending-turn admission, general durable control operations, global shutdown
budget, POSIX ownership, boot/recovery and operation/result correlation. This
unit bounds the named history/fanout structures; it does not claim every native
bookkeeping structure or every pressure scenario is finished. T-LIFE-11 aggregate
stays NOT_RUN pending the rest of its matrix. Durable ACK, managed-work completion
and authorized result publication are still separate unfinished phases.
