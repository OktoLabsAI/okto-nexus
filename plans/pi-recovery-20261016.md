# Pi recovery incident — 2026-10-16

- Three pool openings retained OUTCOME_UNKNOWN receipts, no process birth
  evidence, and occupied shared Core slots. Automatic recovery correctly
  refused to infer stopped resources from absent birth records.
- Verified no Pi processes (including no unreadable Node command lines), then
  used the existing agent-scoped recovery plan/confirm-stopped API. No direct
  database edits, reset or native replay. Slots were released and sessions closed.
- A second blocker remained: runtime.close operation
  op_c7b7bd49a5db34b1b754f8a04d079b6e had DISPATCH_CONNECTION_LOST and no receipt,
  for the already closed ses_cb34e1dde3633cfe5f47aae0e3055652. The reconciler
  required that missing receipt before readiness. The log retains the first
  recovery error, so it continued showing embedded_owned_resources afterward.
- Added retirement of precisely this class of lost close only after existing
  validated ownership release and complete stream replay. Match session owner
  generation; retain an explicit unknown outcome with the release proof, never
  manufacture a successful receipt or permit replay. Other actions are unchanged.
- Nine regression cases passed: eligible/idempotent, live session, active lease,
  mismatched generation, submit action, existing receipt, pending dispatch,
  unrelated error and other executor.
- Real database copied read-only into memory: reconciliation blocked before
  correction and readiness succeeded after correction. Live data untouched.
- Graceful server shutdown completed DRAINED (PID 3596); no forced termination.
- Installed rebuilt Nexus 0.3.1 from `build/pi-recovery-dist`; installed code
  matches source. Restart launcher PID 33752. Live API confirms Pi, Claude and
  Codex Ready; Pi has four WARM/available slots with a parallel limit of five.
  No commit or push performed.

The original opening failures' missing process-birth proof remains a separate
Core lifecycle limitation. This change fixes the lost-close readiness blocker;
it does not claim all unknown openings can now recover automatically.
