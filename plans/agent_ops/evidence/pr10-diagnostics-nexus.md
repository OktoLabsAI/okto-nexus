# DX-07 / DX-14 — shared diagnostics, Nexus qualification

Nexus `doctor` and `participant doctor` accept `--diagnostic-format legacy|v1`.
Legacy remains the default, including existing exit behavior. The v1 projection
uses the existing typed observation once and adds no probe, provider call,
credential read, state repair or authority. Typed stopped/failed service state
maps to the shared `SERVICE_NOT_READY` code only in v1.

All 75 source case identities passed in the isolated installed candidate as well.
The suites overlap completely and are not additive. See the
[installed XML](pr10-correlation/installed/diagnostics/installed.xml),
[import/test qualification](pr10-correlation/installed/diagnostics/qualification.json)
and [source history](pr10-correlation/diagnostics/source/qualification.json).
Nexus wheel SHA-256 is
`991a1995bec626012d113df12c90e897274a83b320373539c28b73c6b4fb7be1`;
the complete [package proof](pr10-correlation/installed/package-proof.json)
compares all 681 raw package files. This is candidate V1. The final OBS-12 V2 wheel is
`fc9bb8f075ac0167eee9c21d96592b12d46c218df77a0f2114f44b1fc20b1355`;
its [package delta](pr10-correlation/candidate-v2/package-delta.json) changes only
two attention modules. Diagnostics and all seven static files are byte-identical,
so the 75-case V1 qualification is retained with its original candidate label.
The separate OBS-12 acceptance is recorded in [PR-10b](pr10-correlation.md).

Both repositories pin common contract digest
`06dbbea77eb0870058bc2fe4c9afc81023ea99f857612984321d1f8e6d20c422`.
The [Connector milestone](pr10-diagnostics-connector.md) is already published as
`12d806f955aea84327dd3a33011016d0283ecc18`, with 93 installed cases and unchanged
Core. This verifies the common declarative schema/vocabulary and mappings, not
a real two-host diagnostic campaign. Real client/provider/vault/service campaigns
and the broader DX-07/DX-14/R3 scope remain open.
