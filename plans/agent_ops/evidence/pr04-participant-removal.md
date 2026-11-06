# PR-04 participant removal and compensation — 2026-11-06

`okto-nexus participant remove` now reviews and compensates the local effects of
an existing participant setup. It performs no Server request and never deletes
the canonical identity or changes key validity, runtime, bindings or grants.
Core's existing exact-owned-entry removal planner and CAS persistence are reused.
Unrelated JSON values and TOML bytes are preserved; protected backups remain.

Approval records retirement and `file_pending` before changing anything. The
file and vault stages are independent, with `vault_pending` and `done` receipts.
Lost file replies recover only from the exact postimage/access policy. Once the
file stage is confirmed, vault retries cannot rewrite later file edits. Confirmed
absent credentials are safe to replay; a locked/unavailable backend is not
absence. Init/connect/launch cannot restore a retired profile, and doctor reports
its retirement without active checks. `--keep-config` explicitly leaves files
alone while removing this setup's vault entry; it makes no removal claim about
manual or changed configuration. Existing clients may still hold the key.

## Validation

- [Source suite](pr04-participant-removal-source.xml): 24 passed. This covers
  JSON/TOML ownership, ACL and backup protection, separate-stage recovery,
  interruption/late edits, explicit keep-config, partial setup, original applied
  but unconfirmed files, stale reviews, retirement guards, diagnostic passivity,
  manual profiles, native error classification and missing-profile behavior.
- [Additional source native-vault case](pr04-participant-removal-vault-source.xml):
  one passed. The real Windows Credential Manager stored a fixture agent key in
  the temporary setup's isolated namespace. Removal and repeated absent removal
  succeeded; a direct native read confirmed `ERROR_NOT_FOUND`. Cleanup ran in
  `finally`. No personal key was read, replaced or rotated.
- [Installed regression suite](pr04-participant-removal-installed.xml): 108 passed
  outside checkout with `python -I`, including init, launch, participant/managed
  doctor, provider vault and HTTP-only CLI. The provider suite also used its
  existing isolated Windows vault roundtrip. See its
  [artifact identity](pr04-participant-removal-full-suite-wheel.json).
- [Final installed checks](pr04-participant-removal-installed-final.xml): four
  passed on the final wheel after improving only the removal failure guidance.
  These overlap the 108-case suite and cover the new message, retirement, actual
  Windows vault removal, protected-ACL compensation and explicit keep-config.
- [Final artifact](pr04-participant-removal-wheel.json): 449 Python files and
  seven static assets byte-match source. Connector/Core and their pins are
  unchanged. [Console evidence](pr04-participant-removal-cli.json) covers the
  new help route and absent-profile refusal without directory creation.

## Failures corrected

The [first source run](pr04-participant-removal-source-initial.xml) had one pass
and one failure: it expected removal to restore the entire original TOML byte
stream. The corrected test verifies the exact bytes outside the owned table and
semantic preservation. Core deliberately retains the separator before that table;
it does not restore a stale whole-file backup.

The [second run](pr04-participant-removal-source-acl-initial.xml) had 14 passes and
one failure that exposed an actual Windows ACL preservation issue. The descriptor
API cleared `AUTO_INHERITED` on a protected DACL. The protected named-security API
preserves that flag without merging parent ACEs; unprotected DACLs continue to use
the descriptor API. Exact owner/DACL verification still occurs before bytes are
written. The [native ACL comparison](pr04-participant-removal-acl.json) records the
observed controls and equality results without user SID values. Failed reports
are retained with only cosmetic trailing whitespace normalized.

Protected keyring absence/error handling was checked against the official
[SecretService](https://github.com/jaraco/keyring/blob/main/keyring/backends/SecretService.py)
and [macOS](https://github.com/jaraco/keyring/blob/main/keyring/backends/macOS/__init__.py)
adapters; their behavior is tested with injected backends here, not native
Linux/macOS campaigns.

## Remaining scope

This completes the tested Windows participant compensation flow, not PR-04 or
R3 as a whole. Already-running clients are not killed or remotely revoked.
Receipts, directories and protected backups remain for inspection. An approved
uncertain file removal with subsequent edits stops for inspection instead of
claiming ownership or rewriting data. Cooperating file writers share the Core
lock; noncooperating writers can still race the final check/replace.

The OS vault was qualified using synthetic credentials in temporary namespaces.
The complete real-vault → interactive real-client → canonical cooperation chain,
actual GUI/TUI behavior, cooperation smoke, other-platform qualification, native
user-service and productive M1/M2 campaigns remain pending. No provider inference,
service registration, package publication or merge occurred.
