# Pi native event diagnostic, same Windows machine

## Current uninstrumented .56 observation — 2026-10-02

`evidence/native-056-pi-current-ui/` records one successful real-provider cycle
in 322.48 s on Windows/Python 3.13.1, through public Connector CLI subprocesses,
separate Server/daemon processes, actual loopback HTTP/WSS and Windows WinVault.
The diagnostic environment flag was explicitly removed. No synthetic native
factory, native qualification override or Server release-gate override was used.

Opening reached SUBMITTED; lease serial reached 2 before the turn. The turn
succeeded, completed the handoff and executed three native actions (one tool
claim). Close succeeded. Server and daemon exited zero, and campaign credentials
were removed. The test's native-event-pump failure assertion remained enabled.
Installed byte/import verification passed, campaign status is PASS, exit code 0,
and `changed_inputs=[]`.

Verified development wheel SHA-256 values:

- Nexus: `38e0b232fba2703d4c5bba4ebb345919a31ce2f4d061c7a158e89b46d11c1777`.
- Core .56: `7f19885f28b16dbfce66b969ab42c79b9947246416c71147315006b6e618b1f6`.
- Connector: `93d78a75c5ad81bbdd96e648be136f0f6b2cfd0a53f350266a1c9f96fc449104`.

Reproduce in the installed Windows environment with
`OKTO_NEXUS_REAL_CONNECTOR=1`, no `OKTO_NEXUS_PI_STREAM_DIAGNOSTIC`, and
`OKTO_NEXUS_REAL_CONNECTOR_REPORT` set to an absolute output prefix in an existing
evidence directory. Invoke `tools/ci_installed.py test --wheel <nexus-wheel>
--output <fresh-directory> --tests
tests/execution_r4/test_real_connector_providers.py::test_real_provider_through_public_connector_cli[pi_rpc]`.
The campaign requires the user's already configured local Pi sign-in; credentials
are not copied into evidence. The final report is `provider-pi_rpc.json`.

This extends actual Pi evidence to the current development packages without the
diagnostic wrappers. One successful cycle neither identifies nor fixes the prior
intermittent .55 stream failure, and does not establish sustained-load, browser,
independent-host or complete provider/platform acceptance. Those remain open.

## Earlier .55 observations

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
