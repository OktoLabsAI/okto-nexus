# Following work in Home

Home keeps three columns. Choose the project in Home to scope the board, or use
All projects to see each card's project. Add harness uses the existing connection
flow; viewing a card does not connect a new runtime or start work.

| Column | What it contains |
| --- | --- |
| Active | Registered harness connections being followed, including current work and confirmed idle sessions. An unconfirmed or disconnected connection is labelled explicitly. Registration alone does not mean connected. |
| Needs You | Questions, approvals, decisions and verification requests. A harness waiting entirely on the user moves here with its requests. If another session is still working, the harness stays in Active and the request appears here separately. |
| Results | Explicit turn outputs, task deliveries and reported completions. A result does not remove its harness connection from Active. |

Working means there is current evidence of productive execution. Idle requires a
current, ready persistent session and complete evidence that no work or action
is pending. Queued, no active session and unconfirmed are separate states.
Unknown evidence is never shown as confirmed Idle.

Use Follow activity to inspect the connection's exact sessions and retained
output. A single unambiguous session opens directly. With multiple sessions,
choose one explicitly; Home does not select the most recent session for you.
Reading output does not continue a session. Continue this exact session and
Ask for work or chat use the existing canonical controls and their permissions.

For a request, Respond, Review approval or Verify delivery opens that exact
record. With several requests, View actions opens the contextual request list.
Recording a decision is different from the harness applying it and resuming.
While confirmation is missing, Home says so and does not ask for the same
decision again. A submitted write or a delayed Running event cannot prove that
the response was applied. Some adapters do not provide that causal confirmation;
the corresponding status remains unconfirmed rather than claiming a resume.

Results distinguish a turn response from a completed task. Verification appears
only with a canonical verdict tied to the same delivery and claim. A completed
task without that proof is not marked verified. Earlier attempts, failed or
cancelled work, missing capture and pending cleanup keep their own labels.
Reported external completions are not native verification by Nexus.

Pausing the board holds its visual order while you inspect a card. It does not
stop exact-context reads. Identical refreshes do not create a pending update.
A semantic change can be applied without closing the panel. Decisions still
revalidate their current record and authority; revoked access clears protected
context regardless of the board pause.

Ask for work or chat opens the shared operator composer. Choose Chat for a
conversation or Ask for work to delegate a task, then select the intended
recipient and project. These labels preserve the existing canonical actions
and permissions. A late Server capability reply does not replace a form being
edited or a board being read; its presentation change waits until that context,
pause and keyboard focus have been released.

## Compatibility and rollback

This presentation remains behind the existing operational Home opt-in and the
Server Home feature gate. The Server advertises presentation versions in
`/api/v1/info`; the new client explicitly requests version 2 only when offered.
Version 1 and the classic Home retain their compatibility paths and global bell.

The existing operational Home setting can be disabled to return to the classic
presentation. This does not stop the daemon, recreate a service, renew a grant,
change connection IDs, delete data or replay a task. CLI and terminal workflows
remain independent of the dashboard. There is no database migration for these
Home states; new handoff verification events add delivery-reference metadata,
while historical events and receipts remain intact.

Automated fixtures, installed-package tests, browser tests, real harness
campaigns and human evaluation are separate evidence layers. Consult
`NEXUS_HOME_ESTADOS_R1/NEXUS_HOME_ESTADOS_LEDGER_R1.json` for the actual qualified
scope. This guide is not approval to enable the presentation by default.
