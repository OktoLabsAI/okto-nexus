# TR4-14-03 combined fault scenario

The normative entry point now exists: `tests/execution_r4/test_ns14.py::test_ns14_03`.

It passed on the installed Core 0.2.50.dev0 / Connector / Nexus tuple from the shutdown-facts manifest. No product package changed for this test increment. The runner verifies source, wheel and installed package bytes before execution.

## Normative preparation and assertions

| Requirement | Executed proof |
| --- | --- |
| Two runtimes | Two distinct canonical runtime.start operations compose two Core owners; exactly two native openings occur. |
| Late open | The first native opening starts before shutdown and returns only after the public pending response. |
| Stuck close | That late native handle's close remains blocked until backend restoration. |
| Pending release | The second runtime stops, but its release on the shared owned-slot ledger remains blocked. |
| One bounded public deadline | Operator POST requests a 0.1-second budget and returns pending in under one second; repeated POST with a 30-second request preserves the original deadline. |
| Both resources reported | Both session IDs are present, including the unfinished opening; the stopped runtime separately reports pending durable release. |
| Force independent of storage | The late handle's force is observed while both its close and the other runtime's ledger release remain blocked. |
| New admission closed | A fresh canonical start resolution is refused with runtime_draining and creates no third opening. |
| Recovery remains available | Health and existing-operation lookup work; the same runtime tasks and legacy owner lease remain held. |
| Stores retained through producers | Spies on both Core journals and the shared ledger observe no close before restoration; every close occurs after all three backend barriers are released. |
| Same-owner second recovery | Subsequent administrative requests reuse the first deadline; restoring the backends drains the original owners, with two total openings and one force for the late handle. |

The test uses the real Nexus/Core composition and public ASGI HTTP routes with controlled native and storage ports. It is the plan's core_fault_injection layer, not actual-provider or platform acceptance. Earlier installed tests on this same artifact tuple separately cover TCP/CLI and child-serve signal recovery.

## Acceptance accounting

TR4-14-03 is passed for this installed Windows fault-injection campaign. NS14.03 is not declared fully closed: its NS14.02 dependency is unverified in the acceptance inventory, and the broader lifecycle/platform qualifications documented in the delivery plan remain open. No gate is closed by this test.

The initial one-case run and final strengthened one-case run overlap; count one normative scenario, not two independent scenarios. See `test_runs_20261001_ns14_03.json` for commands, artifact hashes and raw results.
