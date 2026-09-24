# P03/P12 — legacy profile absence diagnostics

2026-09-24. Base `58ca69b1afbb04c4272717d8e0028dcb36166e6f`.
Development is isolated in the detached worktree
`D:/Projetos/Techridy/okto_nexus_migration_acceptance_worktree` while the original
main-checkout Linux regression70522 remains frozen. No commits in that worktree;
integration and milestone commit/push will be on feature/v0.2.0 only.

## Reproduced gap

T-MIG-03 requires a diagnostic for potentially damaged/missing historical Agent
fields, without inventing skills or restoring guessed contents. Existing
operator diagnostics listed legacy sessions and a generic restoration sentence,
but no observation about the corresponding canonical profile.

Two production HTTP/MCP tests reproduced the omission at the public diagnostic
response, using existing APIs and no proposed-module imports. RED:2 FAIL11.70s.
One fixture has two historical RUNNING sessions for an Agent with empty
capabilities and missing metadata; the other preserves nonempty private fields.
No personal store or provider is used.

```text
rtk proxy D:/Projetos/Techridy/okto_labs_okto_nexus/.venv/Scripts/python.exe -m pytest -q --tb=short tests/test_runtime_legacy_profile_review.py
```

Run from the isolated worktree above. Main source/tests were not modified.

## Correction under qualification

`SqliteEndpointRepo.legacy_profile_review` observes distinct Agents with
legacy_unlinked sessions. At most101 rows are read,100 returned with an explicit
truncated flag. Only IDs and field-state labels (present/empty/missing/invalid)
are returned, not private field contents. `EndpointService.diagnostics` adds
legacy_profile_review version1 after its existing operator authorization.
REST and MCP use the same response. No migration, dispatch or profile write.

Empty fields can be intentional: damage_confirmed is false, restoration_performed
is false and review_required is a prompt for evidence-based operator review.
The response directs recovery to a trusted backup/audited source, never a guessed
skill from harness kind or session metadata. A truncated result directs an
offline inventory of the remaining historical agents.

The focused test snapshots the full Agent before/after, retains old RUNNING and
unknown-ended timestamps, checks duplicate sessions produce one Agent review,
denies caller access over both surfaces and observes zero connector construction.
The preserved-field case checks that private contents do not enter diagnostics.

Initial expanded Windows execution29774 completed32 PASS66.43s. After adding malformed-field and boundedness cases, final expanded Windows60604 completed38 PASS85.46s:

```text
rtk proxy D:/Projetos/Techridy/okto_labs_okto_nexus/.venv/Scripts/python.exe -m pytest -q --tb=short tests/test_runtime_legacy_profile_review.py tests/test_runtime_endpoints.py tests/test_runtime_admin_surfaces.py tests/test_import_boundary.py
```

Linux focused execution47827 completed8 PASS27.98s using the same isolated worktree:

rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_nexus_migration_acceptance_worktree /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest -q --tb=short tests/test_runtime_legacy_profile_review.py

Ruff and diff checks PASS. Content hashes are recorded in evidence/p03-legacy-profile-review-worktree.json. These narrow runs overlapped the main full Linux suite; their durations are not performance measurements. Integration and trusted-source restoration procedure evidence remain pending; do not promote the full T-MIG-03 or phase.

Next: finish the narrow correction and transfer only reviewed paths after the
main Linux suite is terminal. Continue migration history/backfill/cutover/rollback
stimuli and the remaining original plan; final gate NOT PASSED.
