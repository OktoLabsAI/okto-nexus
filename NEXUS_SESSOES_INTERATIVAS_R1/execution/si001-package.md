# SI-001 baseline, version bumps and package check

All three `main` refs were fetched. The new feature branches start at their
existing feature heads. Nexus already contains the Home and Quick Connect
work and the polish from the user evaluation. The fixed analysis baseline
is its ancestor. The Connector and Core heads match the packet baseline.
Repository status, exact refs, workflow hashes and current wheel provenance
are in [si001-baseline.json](si001-baseline.json) and
[si001-wheel-source.json](si001-wheel-source.json).

| Component | New branch | Commit or artifact |
| --- | --- | --- |
| Nexus | `feature/v0.3.8` | The commit containing this record. Wheel SHA-256 `175d77824037b5d3dfde67aea0e8283581843a7e876f77eb4ad3c16fa42a245d`. |
| Connector | `feature/v0.0.14` | `b360b15`. Wheel SHA-256 `184c29b81274a1167ffa765b15433413f126a689c73c5f7a3077ddf0ef9860d2`. |
| Core | `feature/v0.0.15` | `c706d19`. Wheel SHA-256 `02c9454d10633ba760ac1c2d268e84704fbba607a2295ed3161a1df5e5f66657`. |

The new Core and Connector builds differ from the prior wheel package
payloads only in their respective `__version__` declarations after line
ending normalization. Both consumers use the exact same Core wheel. R4
wire revision stays unchanged. Existing validation evidence retains its
original candidate and layer. Future session interaction behavior needs
dedicated tests.

On Windows with Python 3.13.1, the copied plan validator passed and both
Core contract generators passed their checks. All three wheel and source
archives built offline. Core and Connector distributions passed Twine.
The Nexus lock was regenerated with `--find-links vendor/wheels`, then
passed the same offline lock check with no unrelated dependency upgrades.
The initial attempt omitted the local wheel source and could not resolve
the unpublished new Core.

An empty venv installed the Nexus wheel with `serve-lite,dev`, the pinned
Core wheel and the Connector wheel simultaneously. `uv pip check` passed.
Isolated imports resolved all three versions inside the venv and reported
Core 0.0.15 at the canonical inventory boundary. The actual HTTP MCP smoke
passed with 54 tools, two isolated identities and a normal canonical
shutdown. These tests did not execute a real harness or provider. The full
installed matrix and native attach capability remain open.

The separate global installation requested by the user uses the tested
Nexus 0.3.7 release candidate and Core 0.0.14 in an isolated `uv tool`
environment. It passed its own dependency check and HTTP MCP smoke. The
user PATH prefers that launcher and the preexisting Connector continues to
use its original Core. This installation predates the work on 0.3.8.

This increment changes package metadata and pins. It has no database
migration. Rollback selects the previous package pair without editing
runtime state. The next increment freezes exact scope and queue controls
using the [existing write path](si002-write-path.md).
