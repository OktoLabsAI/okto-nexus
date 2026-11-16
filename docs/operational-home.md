# Operational Home

Operational Home brings work, decisions and results into the dashboard's first
screen. The terminal remains a complete way to use Nexus; visiting Home is
optional. This presentation does not start an agent or grant execution access.

During qualification, select **Use operational Home** above the classic Home.
Select **Use classic Home** to return. The preference belongs to this browser;
switching presentation does not stop the daemon, change grants, acknowledge
messages or alter Core/Connector execution. The default remains classic until
the HOME-R1 rollout gate is qualified.

## Read the overview

Choose a workspace in the dashboard header. **All workspaces** is the authorized
union, rather than an inferred project. Agent and work-state filters narrow the
overview. Work performed between agents appears without an operator message.

| Area | Meaning |
| --- | --- |
| Running | Distinct logical activities with current evidence of execution. |
| Waiting to start | Work waiting for an owner, dispatch or native start. |
| Needs you | Current actionable Attention occurrences, with their own priority and snooze state. |
| Server | Authorized incidents that apply to the Server as a whole, when reported by a canonical source. Separate from project counters. |
| New results / Recent results | Unseen results where the canonical occurrence tracks viewing; recent results where it does not. An unknown count is not zero. |
| Work | Logical handoffs, productive deliveries and direct turns. Attempts and controls remain attached to their work. |
| Agents | Identity and reported presence/connectivity. An open session does not prove work is running. |
| External reports | Source-qualified external telemetry, separate from native work and completion. |

The counters use different units and should not be added into a task total.
The **Server** section stays independent of project and agent filters. A global
incident does not mean every project has that incident. Project counters exclude
it, including in All workspaces. Global agent connectivity alone does not create
a Server incident.

A [synthetic example of the Server section](../plans/home_evolution/evidence/pr08-server-attention-browser/quiet-server.png)
shows how global incidents remain visible while the selected project is empty.
**Claimed** means an agent assumed responsibility. **Accepted by runtime** means
the native request was accepted; neither alone proves execution. A successful
turn can produce a result while its handoff still awaits completion or
verification. Pending cleanup is a separate technical obligation and does not
erase a successful result.

Each section reports its snapshot time and whether it is current, partial,
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

**New request** reuses the Meta-harness composer. Choose **Handoff** for tracked
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

**Load more** stays inside its section. A new snapshot or paging conflict can
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
are in [the HOME-R1 evidence directory](../plans/home_evolution/release-report.md).
Synthetic SQLite, browser and real-harness evidence are recorded separately.
