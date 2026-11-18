# SI-018 retained native launch build

Migration 179 adds an optional private build record to the existing execution session. On managed opening admission, the Server records the version, platform, architecture, content fingerprint, portable build identity when available, and recorded qualification of the exact launch inventory revision and candidate. The record shares the session claim transaction. Older sessions and openings without matching build evidence retain an empty field. The retained mapping still requires the exact opening receipt to associate that build with a native session.

This preserves the opening evidence across the normal pruning of executor inventory snapshots. Later presentation admission must compare the retained build, current Core owner and the capability qualified for that build. A runtime inventory qualification alone does not grant terminal attachment.

## Evidence and rollback

The installed Core 0.0.16 regression passed 107 Python cases. The R4 synthetic test verifies the version, architecture, fingerprint and qualification returned alongside the exact opening and stream. The migration regression seeds an older interrupt and paused input, applies schemas 177 through 179, and verifies that the records and foreign keys survive. The earlier session has no invented build record. Targeted lint, Git diff checks and the strict offline wheel and source archive checks passed.

The new field remains private and the R4 wire format is unchanged. Rollback of the feature after migration 179 requires a schema-179-compatible build. SI-018 stays in progress for presentation admission and cross-harness proof.
