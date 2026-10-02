# CI-only cross-repository artifact

The Connector wheel here is used only by the Nexus integration test suite. It is
not a Nexus runtime dependency, and local embedded execution does not install
or import it. This avoids requiring credentials for the private Connector repo
in pull-request jobs. `manifest.json` fixes both consumer test dependencies by
SHA-256; `tools/ci_installed.py` verifies them before installation and compares
installed package files with the wheels before testing.

The Connector wheel matches consumer commit `0f01d63`, including a typed
refusal when Windows denies independent daemon creation. The documented
foreground remedy is tested under a real restrictive Job Object. Its SHA-256
is `6e294c0ed92993a93f5a16b01eee86e3ff4f8e8c63f941300d3e25fd88a165fc`.
Issue #1 adds an explicit unsupported-platform diagnostic and documents macOS
managed-execution limits, separate from discovery and package installation.
The Core wheel is identical in both consumers, SHA-256
`470eb23b28d917a3a154c2ef7cd9fdddf972ca6402c0668961b4c01909f1b732`.
These are regression inputs, not a final release freeze or provider/remote
qualification. See the M13 reconciliation report for installed checks and
the remaining hosted Windows failures.
