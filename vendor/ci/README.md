# CI-only cross-repository artifact

The Connector wheel here is used only by the Nexus integration test suite. It is
not a Nexus runtime dependency, and local embedded execution does not install
or import it. This avoids requiring credentials for the private Connector repo
in pull-request jobs. `manifest.json` fixes both consumer test dependencies by
SHA-256; `tools/ci_installed.py` verifies them before installation and compares
installed package files with the wheels before testing.

The Connector runtime bytes match source commit
`7f9320832a0659b9eecc3b9376abdb576e7c313e`; that commit and its two predecessors
only changed workflow/tests relative to the previously built artifact at
`211be74009a7f3c4f48eb25961f9860a91825df9`. The Core wheel is the same 0.2.51.dev0
artifact already pinned by Nexus and Connector. These are regression inputs,
not a final release freeze or provider/remote qualification.
