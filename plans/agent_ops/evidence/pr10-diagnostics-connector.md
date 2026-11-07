# DX-07 / DX-14 — shared diagnostics, Connector milestone

Connector commit `12d806f955aea84327dd3a33011016d0283ecc18` is pushed to
`feature/v0.0.12`. Version 0.0.12 and the Core 0.0.14 pin are unchanged.
`doctor --diagnostic-format v1` provides the opt-in shared `okto.diagnostics`
contract. Legacy output/exit behavior remains the default; the explicit Server
probe now also refuses a Server-ID mismatch even if the agent ID matches.

The same 93 cases passed on source and in an isolated non-editable installation.
They overlap completely and are not additive. The 119 package files match source,
detached build, wheel and installation. The wheel SHA-256 is
`580ddc45266e8659abda9eaa834c4e46c95937d6a274769b4c716331e9960703`.
The shared contract digest is
`06dbbea77eb0870058bc2fe4c9afc81023ea99f857612984321d1f8e6d20c422`.

The retained [Connector qualification report](https://github.com/OktoLabsAI/okto-nexus-connector/blob/12d806f955aea84327dd3a33011016d0283ecc18/docs/diagnostics-v1-qualification.md)
and [exact evidence manifest](https://github.com/OktoLabsAI/okto-nexus-connector/blob/12d806f955aea84327dd3a33011016d0283ecc18/docs/evidence/diagnostics-v1/manifest.json)
include original failures, corrected reports, synthetic observation guards,
package/import proofs and staged-byte verification. No real HTTP Server,
personal vault, provider or native service was used or qualified.

The [Nexus projection](pr10-diagnostics-nexus.md) subsequently passed the same 75
case identities on source and in the isolated installed candidate. The common
declarative schema/vocabulary and mappings are now qualified in both packages;
this does not claim a real two-host campaign. DX-07, DX-14, real-client/provider
campaigns and full R3 acceptance are not closed by these diagnostics milestones.
