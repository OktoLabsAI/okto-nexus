# CI-only cross-repository artifact

The Connector wheel here is used only by the Nexus integration test suite. It is
not a Nexus runtime dependency, and local embedded execution does not install
or import it. This avoids requiring credentials for the private Connector repo
in pull-request jobs. `manifest.json` fixes both consumer test dependencies by
SHA-256; `tools/ci_installed.py` verifies them before installation and compares
installed package files with the wheels before testing.

The Connector wheel matches consumer commit `9824b47`, including a typed
refusal when Windows denies independent daemon creation. The documented
foreground remedy is tested under a real restrictive Job Object. Its SHA-256
is `31f7c55beb1c457ddd2626b5841a5f7b28f6c92a2f6c4902f9cbf079e7a2e380`.
The Core wheel is identical in both consumers, SHA-256
`470eb23b28d917a3a154c2ef7cd9fdddf972ca6402c0668961b4c01909f1b732`.
These are regression inputs, not a final release freeze or provider/remote
qualification. See the M13 reconciliation report for installed checks and
the remaining hosted Windows failures.
