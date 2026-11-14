# SVC-T15: retained failures and stop-observation correction

Three real attempts stopped before setup:test. The synthetic reference resolved in the CLI and was excluded from the service environment, but the required service-side unavailable-credential diagnosis was not reached. The criterion remains IN_PROGRESS. The selected branch is terminal-only credential availability; no personal vault access or valid provider login is implied.

The final generation took 150 seconds from STARTING to READY, after the start CLI deadline had already expired. No stage-level timing proves why startup was slow. The later stop CLI read an unavailable HTTP observation as INSTANCE_CHANGED; the source correction retries only GET within the original deadline and requires the same generation, instance and PID before any stop latch or POST. Startup limits remain unchanged.

Canonical normal stop later reported DRAINED for that generation, the native task became inactive, uninstall removed it and retained-file fingerprints matched. The earlier retained-handle observer had expired before the canonical stop, so this package does not assert physical-exit proof for the final attempt. The two earlier attempts retained physical-exit proof.

Source qualification: Nexus15 focused PASS and Connector4 focused PASS, Ruff passes. Original fixture failure and intermediate pass are retained without adding overlapping counts. No installed or real retest is claimed; no new campaign is prepared here.
