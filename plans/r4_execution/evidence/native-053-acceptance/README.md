# Installed native acceptance progress — 2026-10-02

Actual Windows/Python 3.13 development-package campaigns, with executable R4
negotiation and the existing exact native qualification checks:

| Route | Provider | Result |
| --- | --- | --- |
| Local, Connector absent from environment | Codex 0.159.0 | PASS |
| Local, Connector absent from environment | Claude Code 2.1.282 | PASS |
| Local, Connector absent from environment | Pi 0.87.1 | PASS |
| Connector public CLI, actual HTTP/WSS loopback | Codex 0.159.0 | PASS |
| Connector public CLI, actual HTTP/WSS loopback | Claude Code 2.1.282 | PASS |
| Connector public CLI, actual HTTP/WSS loopback | Pi 0.87.1 | PASS |

Each completed open, lease renewal, real provider work, canonical handoff
completion and native close. Codex/Claude exercised explicit operator decisions
and HTTP MCP tools. Local Pi executed three native work actions. Local routes
created no WSS tickets. All three Connector campaigns used Windows Vault,
exited Server and daemon with code zero, and removed campaign credentials.
The separate earlier missing-keyring refusal remains preserved as a failed run.
Remote Pi separately passed in 386.66 seconds, including actual native work
actions, lease renewal, successful close and credential cleanup.

The local-only runner asserts that Connector cannot be imported. The installed
attestations verify every package file byte-for-byte against the recorded wheels
and list interpreter/dependency versions. Native peers and readiness were not
monkeypatched. Staged tests replace obsolete readiness overrides with assertions;
Codex selects the isolated exact qualified 0.159.0 installation. These source
changes await integration after the full regression's inputs are unfrozen.

The current Core wheel and sdist also passed offline installation/resource
verification on Windows/Python 3.13, using a hashed wheelhouse, `--no-index`,
`--no-cache-dir` and isolated interpreters. See `core-offline-win313`.

Scope limits: one Windows machine, development artifacts, no final freeze.
Local Pi uses in-process Server HTTP dispatch and its real native tool bridge;
Codex/Claude use loopback HTTP MCP. Connector campaigns have a separate Server
process, CLI subprocesses and a daemon in the test process. Their generic
topology label must not be read as a separate daemon-service-process proof.
Independent A/B/C hosts, two-Server isolation, Linux/provider matrix, complete
controls/fault campaigns, UI and full regression/CI remain open. The full R4
suite is still running and has failures; no G0–G3 gate is closed.
