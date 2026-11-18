# Operational Home

For the three-column harness board and its current states, see
[Following work in Home](home-operational-states.md). The work-group
presentation described below remains a compatibility path during qualification.

Operational Home brings work, decisions and results into the dashboard's first
screen. The terminal remains a complete way to use Nexus; visiting Home is
optional. This presentation does not start an agent or grant execution access.

During qualification, select **Use operational Home** above the classic Home.
Select **Use classic Home** to return. The preference belongs to this browser;
switching presentation does not stop the daemon, change grants, acknowledge
messages or alter Core/Connector execution. The default remains classic until
the HOME-R1 and UI-R1 rollout gates are qualified.

## Find work in one place

The primary destinations are **Home**, **Conversations**, **Graph** and
**Artifacts**. **Advanced** groups the existing pages by purpose; authorization
continues to apply on every surface. The existing Meta-harness identity is now
labelled Conversations; saved view identities and detail URLs remain compatible.

Choose a workspace in the dashboard header. **All workspaces** is the authorized
union, rather than an inferred project. Home has one **Follow-up** region:
work, related sessions, questions and deliveries appear together in their proven
context. Work between agents and sessions without a productive operation are
included. An idle/open session is not a running task. There is no separate
Harnesses, Executions or Sessions destination.

Use **Active**, **Needs you**, **Results** or **All** to narrow the view. The
initial view also includes recent and tracked unseen deliveries. Optional
details filter agent, harness, host and state. Large groups and their sessions,
questions and results have their own **Load more** controls; totals come from
the authorized backend relation, not from the visible page size.

| Information in the context | Meaning |
| --- | --- |
| Running | Distinct logical activities with current evidence of execution. |
| Waiting to start | Work waiting for an owner, dispatch or native start. |
| Needs you | Current actionable Attention occurrences, with their own priority and snooze state. |
| Server | Authorized incidents that apply to the Server as a whole, when reported by a canonical source. Separate from project counters. |
| New results / Recent results | Unseen results where the canonical occurrence tracks viewing; recent results where it does not. An unknown count is not zero. |
| Work | Logical handoffs, productive deliveries and direct turns. Attempts and controls remain attached to their work. |
| Session / connection | Exact host, project and connection context; a session without a turn stays passive. |
| External reports | Source-qualified external telemetry, separate from native work and completion. |

The counters use different units and should not be added into a task total.
The compact **Server** notice stays independent of project and agent filters. A global
incident does not mean every project has that incident. Project counters exclude
it, including in All workspaces. Global agent connectivity alone does not create
a Server incident.

The global bell opens the complete authorized queue across projects and Server
incidents. An empty Server does not occupy a permanent list beside the work.
**Claimed** means an agent assumed responsibility. **Accepted by runtime** means
the native request was accepted; neither alone proves execution. A successful
turn can produce a result while its handoff still awaits completion or
verification. Pending cleanup is a separate technical obligation and does not
erase a successful result.

Each context reports its snapshot time and whether it is current, partial,
unavailable or disabled. A connected stream does not make an expired external
report current. Stale telemetry becomes unknown; it does not imply an idle
agent. A Herdr `done` report does not complete a Nexus handoff.

## Inspect and act

Select a work item or **Open result** to inspect that exact canonical record.
The drawer revalidates the Server, workspace and record identifiers. A missing
or inaccessible record has no automatic replacement. Browser back/forward and
saved detail links revalidate access too; the link conveys no permission.

Attention actions reuse the existing approval, input, verification and runtime
controls. Review the current request before confirming. A decision being
recorded and its application by a harness are separate facts. When a response
is lost or an outcome is unknown, inspect and reconcile the existing operation;
do not assume it is safe to repeat it.

**New request** reuses the Conversations composer. Choose **Handoff** for tracked
work or **Message** for a conversation, and review the recipient, namespace and
audience. **Continue this session** is different: it resolves the exact existing
session and its current authority. A closed, draining or revoked session is not
silently replaced with another session belonging to the same agent.

Result previews are bounded. Artifact content is fetched only after an explicit
selection through its own authorized endpoint; file content is downloaded
rather than executed as dashboard HTML. **Mark seen** applies only to that
tracked occurrence and revision. Opening Home, inspecting a preview or marking
it seen does not ACK an inbox, approve a request or complete work. Results
without canonical viewing state remain labelled recent.

## Connect or resume a collaborator

**Connect agent** opens the short project connection flow from Home or
Conversations. **Open connection** revalidates that exact recorded connection;
it does not start a session or renew authorization. **Add another harness on
this Server** proposes a separate collaborator using the current project preset.
Choose an observed installation, review the project and Server folder, consent
to its temporary model test, then explicitly Finish. The proposed identity is
created only at canonical Finish. Customize expands additional settings without
requiring the administration grid.

The browser, Nexus Server and Connector host have different authority. Local
installation checks and provider login folders refer to the Server host.
**Use a Connector on another host** supplies a credential-free host-draft
command; run it on that host and have an authenticated operator review the same
draft through the [remote setup flow](remote-project-setup.md). A project name
or local folder alone cannot authorize a remote connection.

An unconfirmed check, test or Finish keeps its original request. Reopen the
same project and identity to recover it; recovery does not silently issue a
second test or grant. Closing the dashboard does not stop the existing service.
Startup at login remains a separately supported, explicitly consented service
option in the [service lifecycle guide](service-lifecycle.md).

## Updates and drafts

Home reuses the dashboard's streams and consolidates business-event hints. A
15-second fallback and source deadlines cover changes without a stream event;
background tabs reduce their refresh work. Returning to the tab revalidates.
These intervals describe refresh policy, not a guarantee of provider latency.

**Pause display** pauses presentation only. Agents continue and sensitive
actions still require current canonical validation. Opening a drawer also
stabilizes the overview while you inspect or edit. A pending-update notice lets
you apply the latest snapshot. Drafts, focus and the selected recipient should
survive read refreshes. Closing or leaving an edited form offers a discard
choice; logout clears protected state.

**Load more** stays inside its context or related partition. A new snapshot or paging conflict can
restart the page set so records from incompatible revisions are not combined.

## Diagnose a problem

- **Unknown total / unavailable section:** refresh or narrow the scope. Other
  sections may still be usable; an unavailable source is not an empty result.
- **Access changed:** authenticate again. Protected lists and drawers are
  cleared after authorization failure; old browser history cannot authorize them.
- **Exact record unavailable:** return to the overview and select a current
  record. Do not infer a replacement from the latest session or a similar title.
- **External source disabled or stale:** inspect its source and validity using
  [external observations](external-observations.md). Native work is independent.
- **Question or runtime operation needs recovery:** use the canonical
  [Attention](attention.md) or [runtime operator guide](harness-integrations/operator-guide.md).
- **Presentation regression:** switch to classic Home. Runtime and terminal
  controls remain available; reverting the presentation requires no data reset.

The implementation contract, reproducible measurements and acceptance ledger
are in [UI-R1](../NEXUS_UI_R1/NEXUS_UI_EXECUTION_LEDGER_R1.json), alongside
the retained [HOME-R1 evidence](../plans/home_evolution/release-report.md).
Synthetic SQLite, browser and real-harness evidence are recorded separately.
