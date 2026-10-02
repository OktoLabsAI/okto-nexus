# Pi native event diagnostic, same Windows machine

The .55 application tuple is unchanged from [the discovery/native report](M13_SAME_MACHINE_055.md).
The test-only `OKTO_NEXUS_PI_STREAM_DIAGNOSTIC=1` wrapper now measures queue
high-water event count/serialized bytes and queue/history append refusals, in
addition to stream exception frames, selection duration and native bridge calls.
It returns the original results and leaves buffer limits, native behavior,
authorization, deadlines and the stream-failure assertion unchanged. The report
contains aggregate counters, not native messages or credential values.

## Retained campaigns

- `evidence/native-055-pi-buffer-diagnostic/`: one pass in 313.44 s. The invocation
  omitted `OKTO_NEXUS_REAL_CONNECTOR_REPORT`, so detailed in-memory diagnostics
  were not exported. Its JUnit/installed/campaign evidence is retained; do not
  infer queue measurements or report-only facts from this attempt.
- `evidence/native-055-pi-buffer-report/`: one pass in 330.22 s with the report
  destination explicitly configured. Peak queue: 64 events and 49,045 serialized
  bytes (independent maxima), no queue refusal, no history refusal and no stream
  failure captured. Eleven selection checks took 0.45–7.83 s; the three native
  action calls returned in 1.19–1.45 s. Lease serial reached 2 before the turn;
  the turn and close succeeded, handoff completed, and three native actions ran.
  Daemon/server exited zero and campaign credentials were removed.

Both campaigns passed installed package verification and recorded
`changed_inputs: []`. Python 3.13.1, Windows, real Pi, loopback HTTP/WSS and the
protected Windows vault were used. The detailed report is `provider-pi_rpc.json`
in the second campaign. Diagnostic instrumentation can affect scheduling.

The preceding uninstrumented .55 failure is preserved in
`evidence/native-055-connector-pi/`. Its underlying cause remains unknown.
These successful observations neither prove that overflow caused that failure
nor establish a fix or sustained-load acceptance. Independent-machine acceptance
remains reserved for the user's later manual session. No gate is closed.

## Core hosted documentation follow-up

Core hosted run [36998004262](https://github.com/OktoLabsAI/okto-nexus-connector-core/actions/runs/36998004262)
completed all six Windows/Linux Python 3.11–3.13 cells. Each Windows cell had
1120 passes/77 skips; each Linux cell 1174 passes/23 skips. Each failed the same
public-doc version assertion; build/offline-install steps were skipped.
Core `9a19ebe` corrects the stale .53 declaration and current hosted guidance;
`10585bb` retains terminal evidence and the three public-doc checks passing on
both installed Windows and WSL environments. These are documentation-only Core
commits; the installed .55 wheel used by the native campaigns is unchanged.
Green hosted requalification and final artifact regeneration remain pending.

The older NS15.05 documentation/acceptance notes now link to existing scoped
TR4-15-05/TN-38/39/40 evidence instead of continuing to call it missing. This is
ledger reconciliation, not another execution or final-artifact acceptance.
