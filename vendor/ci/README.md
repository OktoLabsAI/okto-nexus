# CI-only cross-repository artifact

The Connector wheel here is used only by the Nexus integration test suite. It is
not a Nexus runtime dependency, and local embedded execution does not install
or import it. This avoids requiring credentials for the private Connector repo
in pull-request jobs. `manifest.json` fixes both consumer test dependencies by
SHA-256; `tools/ci_installed.py` verifies them before installation and compares
installed package files with the wheels before testing.

The Connector wheel was rebuilt with the Core 0.2.52.dev0 dependency, matching
consumer commit `acaa192`. Its runtime source is unchanged from `7f93208`;
the new metadata pins the corrected Core lease deadline comparison. Its SHA-256
is `332f5aa8c683f7732a56925598968a3bba61a9d6fb5dcc3909762b016a0340ae`.
The Core wheel is identical in both consumers, SHA-256
`470eb23b28d917a3a154c2ef7cd9fdddf972ca6402c0668961b4c01909f1b732`.
These are regression inputs, not a final release freeze or provider/remote
qualification. See the M13 reconciliation report for installed checks and
the remaining hosted Windows failures.
