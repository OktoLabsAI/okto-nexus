# P07 — native request registration and pending-start close

Parent `1780f15`; branch `feature/v0.2.0`. Partial P07/P08 checkpoint.

Two real scripted-peer reproductions failed before correction:

`.venv/Scripts/python.exe -m pytest tests/test_harness_codex_connector.py -q -k 'fast_native_error or pending_start' --tb=short`

2 FAIL, 31 deselected (`evidence/p07-codex-request-race-red.log`): a native error
arriving before the write returned lost its session attribution; close could
unsubscribe while turn/start still lacked a native identity. The tests delay
the transport boundary around actual pipe traffic, not a mock reply assuming
the corrected implementation.

`_CodexTransport.send_fire_and_forget` now invokes an optional allocation hook
before the write. `CodexAppServerConnector._send_request` registers the native
request ID/session/method first, without holding registry or session locks over
the write. This registry has a finite 64-request admission limit. A write failure
does not erase uncertainty or authorize replay. Successful responses still do
not claim turn completion or alter canonical transport ACK status.

Thread state now records a pending turn/start ID. One thread cannot admit another
normal turn while pending/active. Native start error or turn/started clears that
pending marker. Close shares its existing 2.5-second deadline between waiting
for native identity and waiting for the matching interrupted terminal. Missing
identity/terminal remains explicitly unknown. This extends the earlier
observed-active-only close unit; general durable operation correlation is still
pending. Neither the native pending map nor its integer ID is an authorization
credential or a durable Nexus operation record.

Post-fix targeted: 2 PASS, 31 deselected (`evidence/p07-codex-request-race.log`).
Regression:

`.venv/Scripts/python.exe -m pytest tests/test_harness_codex_connector.py tests/test_runtime_shared_connection.py tests/test_runtime_protocol_limits.py tests/test_runtime_native_campaign.py -q --tb=short`

45 PASS, 4 skipped in 43.43s (`evidence/p07-codex-request-race-gate.log`); native
flags absent and no providers called by this gate. The pending-start fixture
also proves a second normal turn is refused before sending.

Then real Codex, with the explicit isolated campaign configuration/paths from
NATIVE_CAMPAIGN.md:

`.venv/Scripts/python.exe -m pytest tests/test_runtime_native_campaign.py -q -k codex --tb=short`

**2 PASS, 1 deselected in 18.04s**,
`evidence/p07-native-codex-request-race-gate.log`. Both canonical two-turn flow
and active-close/interrupted-terminal flow pass on this working tree, including
the preceding atomic terminal/close change. Each uses a fresh temporary native
configuration/store/project; both owned processes reap. No auth.json remained
under that campaign's disposable pytest directory after completion. Version
previously probed in this same execution: Codex 0.155.1. No extra Claude/Pi/attach
native assertions are inferred from this result.

Changed symbols: `_send_request`, `_send_turn`, `_steer`, `_interrupt`, `_end`,
`_on_notification`, `_on_unmatched_response`, `observe_lifecycle`, `_ThreadState`,
transport allocation hook. Tests: `test_harness_codex_connector.py`.
No migration. Ruff and diff checks pass.

Next: native event buffer/subscriber limits, durable control operations and
operation/result correlation, POSIX ownership/boot recovery. Full matrix and
final gate remain pending; the 64-request saturation path still needs its load
scenario, and successful native responses are not yet durable operation ACKs.
