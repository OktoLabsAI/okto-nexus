# Connector empty discovery diagnostics — 2026-10-02

User evidence from the second Windows computer: standalone `discover` returned
zero candidates and only the trust-policy note. This is a local provider
inventory result, not evidence of LAN connectivity or an independent-host pass.
The remote installation version and provider command locations remain unknown.

Rechecked the open Connector issue list: issue
[1](https://github.com/OktoLabsAI/okto-nexus-connector/issues/1) includes both
unsupported macOS containment and empty discovery. The existing documented
Windows/Linux platform scope remains unchanged. No macOS backend is claimed.

The Connector now explains empty discovery in human and JSON output, distinguishes
standalone discovery from a registered executor's approved roots, and points to
read-only local command lookup and persisted configuration. No paths are approved,
providers executed, credentials read or network peers selected by this change.

Also corrected an actual CLI inconsistency: candidate display and availability
previously used separate scans, and the second scan omitted `--harness`.
Both now use one filtered collection of complete Core candidates. Core assessment
failures produce a Connector error instead of silently omitting availability.

Validation on Windows/Python 3.13.1: 30 source tests and 30 installed-wheel tests
passed across discovery diagnostics, persisted discovery, platform doctor and
Core catalog integration. All 75 installed Connector package files matched the
wheel; dependency check passed for the isolated 51-package environment.

Wheel SHA-256: `78b453222407df19028289f2a4b5ee02fb096d9d6c2c1a1437d481aa7e6f7c14`.
Evidence: [source tests](evidence/discovery-diagnostics-source.xml) and
[installed tests](evidence/discovery-diagnostics-installed.xml).

An initial invocation failed to set PYTHONPATH because of nested PowerShell
expansion and therefore tested the previous installed wheel: 5 new tests failed
and 18 existing tests passed. Correct source selection used pytest's explicit
`pythonpath=src`; final installed validation used `-I` and an empty pythonpath.
The earlier invocation is not counted as a pass.

This is a development Connector artifact, not the final three-package M13 freeze.
The Nexus vendored Connector has not been replaced by this diagnostic-only wheel.
Independent-host acceptance, R4 UI completion and final release gates remain open.
