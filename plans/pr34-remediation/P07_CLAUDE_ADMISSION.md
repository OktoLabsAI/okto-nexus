# P07 — bounded Claude stream pending-turn admission

2026-09-23, Windows, feature/v0.2.0; parent SHA 7e3e774. No migration.

Claude stream retained one FIFO marker for every submitted unresolved turn,
without an admission limit. _send_turn now checks pending turns plus concurrent
steer reservations under _state_lock. _steer reserves before any interrupt or
replacement write and releases its reservation in finally. Limit: 32 outstanding
turns/reservations per connection. CONFLICT reason pending_turn_capacity rejects
excess input without a native write; interrupt/end remain available. A native
result frees a FIFO entry. A write failure with uncertain acceptance does not
silently free that pending entry or authorize replay.

Symbols: ClaudeCodeStreamConnector._send_turn/_steer/_steer_reserved,
_check_turn_capacity and _pending_admissions. Existing protocol/control semantics
unchanged; these are admission bounds, not durable operation/claim correlation.

The initial fixture omitted HarnessCommand.session_id and failed with TypeError.
That was a test defect, not a behavioral RED. After fixing the fixture, the
committed baseline module (7e3e774) was temporarily tested and the worktree module
restored in finally. The valid RED admitted all 40 concurrent inputs, exceeding
the intended capacity of 32. No unrelated files were restored or modified.

Commands are executed via rtk proxy:

- `.venv/Scripts/python.exe -m pytest tests/test_runtime_claude_admission.py -q --tb=short`:
  1 behavioral FAIL on baseline; evidence/p07-claude-admission-red.log.
- `.venv/Scripts/python.exe -m pytest tests/test_runtime_claude_admission.py tests/test_harness_claude_code_connector.py tests/test_runtime_event_buffers.py -q --tb=short`:
  45 PASS, 7 skipped in 65.42s; evidence/p07-claude-admission-gate.log.
- `.venv/Scripts/python.exe -m pytest tests/test_runtime_native_campaign.py -q -k claude_code --tb=short`:
  fresh REAL isolated Claude two-turn production campaign: 1 PASS, 2 deselected
  in 9.36s; evidence/p07-claude-admission-native.log. Uses the same explicitly
  authorized executable/login-source paths in NATIVE_CAMPAIGN.md; temporary auth
  copy removal is in the fixture's finally block. No personal sessions/settings.

The disposable pipe peer records actual incoming frames: exactly 32 user inputs,
no interrupt from refused steering, successful explicit interrupt while full,
and resumed admission after a native result. This is a native transport fixture,
not a real Claude model pressure/steering claim. Existing production-composition
overflow tests and the real two-turn campaign cover integration separately.
Ruff PASS. Seven skipped legacy native tests remain NOT_RUN, not PASS.
Codex/Pi/attach native NOT_RUN for this unit.

Remaining P07 dependencies: global shutdown budget, POSIX birth ownership,
boot/recovery and full controls/multiplexing/adversarial matrix. Durable operation,
handoff, causal budgets and result publication are still later unfinished units.
Final gate NOT PASSED.
