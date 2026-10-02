# Core .56 coordinated adoption — 2026-10-02

Nexus and Connector now use the same reviewed Core .56 wheel (`7a964db`).
Connector adoption is committed at `3e9c607`.
Nexus's runtime inventory version guard, both serve dependency pins, uv lock
and CI artifact manifest agree. Connector's declared dependency and README agree.
The change adopts passive physical-payload discovery for known POSIX layouts;
it does not grant trust, run a provider or qualify native macOS containment.

## Installed integration

Each of Windows Python 3.13.1 and same-machine WSL Linux Python 3.12.13 passed
35 Nexus checks covering local discovery, Core catalog/inventory, automatic
daemon startup, HTTP inventory refresh and local realization/consent. Durations
were 152.73 and 114.55 seconds respectively. The runner verified every installed
package file against the three wheels, imported from site-packages with isolated
Python outside the checkout, and recorded no changed campaign inputs.
Evidence: `evidence/posix-discovery-056-{windows,linux}/`.
The shared HTTP client deprecation warning remains recorded.

Connector separately passed 48 installed discovery/inventory/diagnostic checks
on each OS. Its operational docs audit passed 37 commands and 12 links.
Core's preceding full installed suites passed 1121 tests/95 skips on Windows
and 1192/24 on Linux; these remain separate scopes, not additive unique coverage.

## Artifacts

| Artifact | SHA-256 |
| --- | --- |
| Core .56 wheel | `7f19885f28b16dbfce66b969ab42c79b9947246416c71147315006b6e618b1f6` |
| Connector 0.5.0.dev0 wheel | `b77e7c020a3e17dba69200f7f88c8a96fab273c29a6fcb941c7221f58ceaedf2` |
| Connector sdist | `6be7f9ba29e3020e04166feb64420a23b742324a751bdf8d31fa819608c40c1f` |
| Nexus 0.2.0 wheel | `59d06d0a8f0069bf569ed65c04cc15b721383d0b27d81793fbeb71682e3d27d2` |
| Nexus sdist | `b472d9b635c04dcaeefd4eb37359a8250e8b914294bf47f41d02e5c6a90dc3b0` |

The isolated Nexus build regenerated frontend assets from reviewed sources;
pre-existing user changes to static build outputs in the checkout were preserved.

## Clean installation

New Windows Python 3.13.1 and WSL Linux Python 3.12.13 environments passed
`tools/ci_installed.py install` and `smoke` with the exact wheels above.
The base package booted without Core,
Connector or torch; serve-lite then booted without Connector or torch, returned
HTTP 200 for protocol/dashboard and 401 for unauthenticated operator access.
Connector was installed last. Full installed package-byte verification and
`pip check` passed on both OSes. Evidence is in
`evidence/posix-discovery-056-clean-{windows,linux}/`.

Reproduce in a fresh environment: run its Python against
`tools/ci_installed.py install --wheel <Nexus-wheel> --output <evidence-dir>`,
then the same command with `smoke`, and `python -m pip check`.
Dependency artifacts are selected and hash-checked by `vendor/ci/manifest.json`.
This online dependency installation is not an offline wheelhouse proof.

## Remaining acceptance

These development packages do not freeze the final three commits or close M13.
Full current Nexus/Connector regression and hosted CI, remaining UI/native
provider journeys, fault recovery and final matrix still require completion.
The Pi event-stream intermittency remains open. Core `43f31ec` subsequently
corrected the reproduced retained-obligation test fixture; its hosted
requalification remains pending, with GitHub account billing restrictions
preventing jobs from starting in run 37001262922.
All local Linux work is WSL on the same machine. Independent-host
acceptance remains manual with the user; no remote-machine result is inferred.
The user's global CLI installation was not replaced.
