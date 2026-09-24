# Remediation evidence for 0.2.0

The [execution status](../../plans/pr34-remediation/IMPLEMENTATION_STATUS.md)
records the current branch, completed milestones and live verification runs.
The [finding audit](../../plans/pr34-remediation/P12_FINAL_AUDIT.md) links all
15 findings to implementation and scoped evidence. The original129 acceptance
rows and their outcomes remain in [the backlog](../../05_BACKLOG.json).

Current full regression and release acceptance are **pending**. Selected passing
tests do not constitute a full release gate. Historical red reproductions,
preparation failures, platform skips and storage failures are retained in their
generation-specific manifests; overlapping run counts are never added together.

| Evidence | Scope |
|---|---|
| [External attach work](../../plans/pr34-remediation/P12_ATTACH_WORK_INTEGRATION.md) | Authenticated claim/ACK/complete, older-writer fence, retention/recovery; isolated fixtures and actual POSIX fixture socket |
| [Context observation](../../plans/pr34-remediation/P12_MIRROR_OBSERVATION.md) | One executor with optional nonexecuting observers; fifth test adapter |
| [Native frames](../../plans/pr34-remediation/P12_NATIVE_FRAMES.md) | Approved local Codex/Claude campaigns at their recorded SHA/version; classified native commands and events |
| [Recovery under load](../../plans/pr34-remediation/P12_RECOVERY_PRESSURE.md) | Repeated same-store owner crash/recovery with measured contention and resource bounds |
| [Comparable performance](../../plans/pr34-remediation/P12_COMPARABLE_PERFORMANCE.md) | Same-environment baseline/current synthetic comparison, including measured higher latency |
| [Upgrade and rollout](../../plans/pr34-remediation/P12_MIGRATION_ROLLOUT_INTEGRATION.md) | Additive migration, legacy preservation, writer compatibility and safe disable/cutover |
| [Backup and restore](../../plans/pr34-remediation/P12_COMBINED_BACKUP_RESTORE.md) | Offline combined database/journal/artifact consistency and restoration |

Pi native and dedicated installed Claude attach are NOT_RUN under the approved
campaign scope. A synthetic peer proves Nexus behavior, not provider support.
The older [PR evidence index](evidence/EV-INDEX.md) is preserved for history and
must not supply current run counts or credentials/endpoints for a new campaign.

Raw new logs and JUnit XML remain in private task directories because failures
can contain fixture credentials. Committed manifests omit captured payloads and
retain test identities, outcomes, source hashes, commands and limitations.
