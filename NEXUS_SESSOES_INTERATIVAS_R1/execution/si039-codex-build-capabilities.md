# SI-039 capability grants for the exact Codex build

The installed Core 0.0.16 wheel evaluated the real Windows x64 executables
for Codex 0.170.0 and the archived 0.157.0. The probe selected their native
executable files explicitly and ran only `--version` in a disposable profile
with a minimal environment. It measured the build identities and fed those
candidates through the normal executor-inventory snapshot and schema
validation. Both candidates were eligible for a protocol probe.

| Build | Qualification | Conversation grant | Qualified controls |
| --- | --- | --- | --- |
| Codex 0.157.0 | Qualified | Yes | Interrupt and steer |
| Codex 0.170.0 | Unqualified | No | None |

No app-server or model request ran as part of this comparison.
The inventory is a passive assessment. It does not contain an observed
session capability report. This comparison used explicit paths and did not
test PATH discovery through the npm shim.

The 16 existing Core regressions on the installed wheel covered exact grants
and rejection across changed build identity, platform and adapter. The
0.170.0 result preserves the scope of its separate viewer compatibility
evidence. SI-T-I06 still needs the campaign layer and the remaining
harness coverage. [Inventory observations](si039-codex-build-capabilities.json) [Earlier viewer probe](si004-codex-ephemeral-owner-windows.md)

This increment changes evidence and ledger links. Reverting the commit
removes those records without a schema or runtime rollback.
