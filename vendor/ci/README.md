# CI dependencies for Nexus 0.3.0

Core 0.0.10 is a mandatory runtime dependency. Connector 0.0.8 is used only by
the cross-repository integration tests; it is not a Nexus runtime dependency.
Both wheels are built from the versioned development branches. Connector pins
the same Core version. These artifacts are for validation before publication.

`manifest.json` records their SHA-256 digests. `tools/ci_installed.py` verifies
the hashes before installation and compares installed files with these wheels
before testing. CI uses these artifacts before the matching PyPI versions exist.
