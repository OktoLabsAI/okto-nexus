# Runtime lifecycle plan — closure audit

Date: 2026-10-20. Scope: local embedded Nexus and a Connector in a separate
process on the same host, as authorized by the user. A physically separate
Connector host is a later campaign. The ledger records all milestones M0–M8
and UI-A/B/C as complete in this scope.

| Requirement | Current evidence |
| --- | --- |
| M0 baseline and M1 birth record | [M0](m0-validation.md) and [M1](m1-validation.md) results; version pins and feature branches verified in all three clean repositories. |
| M2 durable intent, containment and crash recovery | [M2 acceptance](m2-final-acceptance.md), Core/Connector 8/8 CI jobs and Nexus 24/24 installed jobs. |
| M3 independent recovery and availability | [M3 acceptance](m3-final-acceptance.md), [UI-A](ui-a-installed-restart-evidence.md), [UI-B](ui-b-evidence-audit.md), installed load and global Pi recovery. |
| M4 bounded pending reconciliation and stream fairness | [M4 acceptance](m4-final-acceptance.md), including the retained measured physical file audit and local Connector restart UI. |
| M5 shared embedded/Connector recovery | [M5 differential audit](m5x-differential-evidence-audit.md) and [separate-process receipt recovery](m5y-separate-process-receipt-recovery.md). |
| M6 independent supervisor experiment | The Connector supervisor ADR and [real UI experiment](m6d-real-ui.md) are recorded in the ledger. The plan did not mandate adopting the experimental supervisor. |
| M7 pool, queue and load | [UI-B audit](ui-b-evidence-audit.md), [installed load](m7o-installed-load-results.md), and [unlimited-mode UI](m7r-ui-unlimited-and-expired-grant.md). |
| M8 installed qualification and rollout | [Fixed acceptance audit](m8-fixed-acceptance-audit.md), [backup](m8-final-prewheel-backup.md), [global CI-wheel rollout](m8-global-ci-wheel-rollout.md), and all three UI gates. |

The final product code was tested as installed wheels: Core run
[39336889894](https://github.com/OktoLabsAI/okto-nexus-connector-core/actions/runs/39336889894)
8/8, Connector run
[39343006146](https://github.com/OktoLabsAI/okto-nexus-connector/actions/runs/39343006146)
8/8, and Nexus run
[39472894540](https://github.com/OktoLabsAI/okto-nexus/actions/runs/39472894540)
24/24. Changes between those CI commits and the current feature-branch heads
are documentation only in all three repositories. The global installed
Nexus wheel records the same SHA-256 as the successful Windows CI artifact.
The UI directly showed Pi, Claude and Codex Online, and a new Pi turn returned
the exact response `M8_PI_CI_WHEEL_OK` with 1/1 ACK. The consumed session
retired, and the four configured warm Pi instances remained available.

The prior unexplained stop of the global Server remains an observation, not a
diagnosed product fault. The completed gates prove automatic recovery once
the Server starts with stable configuration, not autonomous restart of an
absent Server process. Historical L3/L12 incidents also lack causal proof;
current installed behavior passed the recorded recovery and load cases.
PRs, merges to `develop`/`main`, tags and PyPI publication are explicitly a
separate phase of the plan and have not been performed for these versions.
