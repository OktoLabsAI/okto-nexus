# CI-only cross-repository artifact

The Connector wheel here is used only by the Nexus integration test suite. It is
not a Nexus runtime dependency, and local embedded execution does not install
or import it. This avoids requiring credentials for the private Connector repo
in pull-request jobs. `manifest.json` fixes both consumer test dependencies by
SHA-256; `tools/ci_installed.py` verifies them before installation and compares
installed package files with the wheels before testing.

The Connector wheel uses the Core 0.2.53.dev0 pin, including a typed
refusal when Windows denies independent daemon creation. The documented
foreground remedy is tested under a real restrictive Job Object. Its SHA-256
is `68df39616fd8567306f2de8c63fe7a41380ae7603f3e03b244705266083d75cd`.
Issue #1 adds an explicit unsupported-platform diagnostic and documents macOS
managed-execution limits, separate from discovery and package installation.
The Core wheel is identical in both consumers, SHA-256
`cc873031378793d374a9bbc00572c7a525f99c4246324a941713d866cc62c6b1`.
These are regression inputs, not a final release freeze or provider/remote
qualification. See the M13 reconciliation report for installed checks and
the remaining hosted Windows failures.
