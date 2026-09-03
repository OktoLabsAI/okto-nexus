// Help modal - the Pulse HelpPanel pattern: section list on the left,
// scrollable content on the right, Nexus-specific topics.

import { type ReactNode, useState } from "react";
import {
  Activity,
  Bot,
  Brain,
  CheckSquare,
  Files,
  FolderOpen,
  KanbanSquare,
  KeyRound,
  MessageSquare,
  MessagesSquare,
  Rocket,
  Settings,
  Shield,
  ShieldAlert,
  Tags,
  TerminalSquare,
  Waypoints,
  X,
} from "lucide-react";

interface Section {
  id: string;
  title: string;
  icon: ReactNode;
  content: ReactNode;
}

const H = ({ children }: { children: ReactNode }) => (
  <h3 className="font-display font-semibold text-sm text-surface-900 dark:text-surface-100 mt-4 first:mt-0 mb-1.5">
    {children}
  </h3>
);
const P = ({ children }: { children: ReactNode }) => (
  <p className="text-xs text-surface-600 dark:text-surface-400 leading-relaxed mb-2">
    {children}
  </p>
);
const Code = ({ children }: { children: ReactNode }) => (
  <pre className="text-[11px] font-mono bg-surface-100 dark:bg-surface-900 border border-surface-200 dark:border-surface-700 rounded-lg p-2.5 overflow-x-auto mb-2 text-surface-700 dark:text-surface-300">
    {children}
  </pre>
);
const Li = ({ children }: { children: ReactNode }) => (
  <li className="text-xs text-surface-600 dark:text-surface-400 leading-relaxed">
    {children}
  </li>
);

const SECTIONS: Section[] = [
  {
    id: "quickstart",
    title: "Quickstart",
    icon: <Rocket size={14} />,
    content: (
      <>
        <H>Start the hub</H>
        <Code>okto-nexus serve</Code>
        <P>
          That's it: the dashboard opens at http://127.0.0.1:8202 with no key
          (local access is trusted by design). Data lives in ~/.okto_nexus.
        </P>
        <H>Connect your first agent</H>
        <P>
          Go to <b>Agents → New agent</b>, name it (e.g. researcher) and copy
          the MCP snippet shown — the key appears a single time. Paste it
          into your client (Claude Code, Cursor, VS Code…) and the agent
          shows up on the graph as soon as it opens a session.
        </P>
        <H>Watch it live</H>
        <P>
          The graph shows presence and traffic in real time (the ● Live chip
          at the top). Click any element to inspect it.
        </P>
        <H>Send a smoke-test message</H>
        <P>
          Open <b>Meta-harness</b>, choose Message, select an audience and send
          a turn. Replies appear in the same conversation, so it is the fastest
          way to confirm that an agent is connected and responding.
        </P>
      </>
    ),
  },
  {
    id: "agents",
    title: "Agents & keys",
    icon: <KeyRound size={14} />,
    content: (
      <>
        <H>Key-based identity</H>
        <P>
          Every agent owns an <code>nxs_…</code> API key. Only the hash is
          persisted; the plaintext appears ONCE at creation or regeneration —
          store it right away. MCP connections always require a key; the
          local dashboard does not.
        </P>
        <H>Lifecycle</H>
        <ul className="list-disc pl-4 space-y-1 mb-2">
          <Li>
            <b>Regenerate key</b>: the old key dies immediately; the new one
            is shown once.
          </Li>
          <Li>
            <b>Deactivate</b>: revokes access while keeping history
            (reversible).
          </Li>
          <Li>
            <b>Delete</b>: removes a regular agent identity for good. The
            reserved <code>operator</code> identity powers dashboard messaging
            and Meta-harness, so neither the UI nor the API allows deleting it.
          </Li>
        </ul>
        <H>Permissions & presets</H>
        <P>
          Every agent carries communication permissions: direct messages,
          broadcasts, channel posts, handoff create/work/cancel, plus
          fine-tuning limits (rate per minute, max recipients, an allowlist
          of direct peers). Assign a <b>preset</b> at creation (Full access,
          Coordinator, Worker, Observer — or your own) and customize flags
          per agent at any time; changes apply immediately on every
          transport. Manage custom presets in the{" "}
          <b>Permission presets</b> tab (clone a built-in to start).
        </P>
        <H>Migrating stdio (V1) agents</H>
        <Code>okto-nexus admin issue-keys --project-root .</Code>
        <P>
          Issues keys in batch only for agents that have none (additive and
          idempotent).
        </P>
      </>
    ),
  },
  {
    id: "graph",
    title: "Graph",
    icon: <Waypoints size={14} />,
    content: (
      <>
        <H>How to read it</H>
        <P>
          Use <b>Agent representation</b> at the top of the Graph to switch
          between the full <b>Detailed</b> cards and compact <b>Simple</b>{" "}
          circles. The choice is remembered without changing the graph layout
          or your current inspection.
        </P>
        <ul className="list-disc pl-4 space-y-1 mb-2">
          <Li>
            <b>Agent colour = identity</b>: the configured profile colour, or
            a stable colour derived from the agent ID when none is set.
          </Li>
          <Li>
            <b>Status dot = presence</b>: green means online, amber means
            stale, and grey means offline. In Simple mode it sits on the
            circle's upper-left edge.
          </Li>
          <Li>
            <b>Simple circle size = current activity</b>: active sessions plus
            unread and in-flight inbox work, on a bounded scale.
          </Li>
          <Li>
            <b>Blue arrows</b>: messages in the last 24h; thickness = volume.
          </Li>
          <Li>
            <b>Cyan arrows with an N ✉ badge</b>: in-flight traffic
            (delivered but not yet read).
          </Li>
          <Li>
            <b>Magenta squares</b>: open handoffs awaiting a claim; magenta
            edges: claimed handoffs.
          </Li>
        </ul>
        <H>Inspection</H>
        <P>
          Click an agent to see its inbox lanes, sessions (with close) and
          its conversations in chat form, split per peer — including the ⚠
          tab with sends that resolved to no recipient. Click an edge for the
          pair's conversation; click a magenta square for handoff details and
          cancellation. The panel resizes from its left edge.
        </P>
      </>
    ),
  },
  {
    id: "messages",
    title: "Messages",
    icon: <MessagesSquare size={14} />,
    content: (
      <>
        <H>Delivery lanes</H>
        <ul className="list-disc pl-4 space-y-1 mb-2">
          <Li>
            <b>unread</b>: delivered to the inbox, not pulled yet.
          </Li>
          <Li>
            <b>delivered</b>: pulled via inbox_pull, under lease (without an
            ack it returns to unread).
          </Li>
          <Li>
            <b>read</b>: confirmed via inbox_ack.
          </Li>
          <Li>
            <b>parked</b>: set aside by the recipient for later.
          </Li>
        </ul>
        <H>History</H>
        <P>
          The Messages view filters by lane and agent, with pagination. Sends
          whose target resolved to nobody show the "no recipient" badge —
          sends to a nonexistent agent_id are rejected without a trace (full
          rollback, by bus design).
        </P>
      </>
    ),
  },
  {
    id: "handoffs",
    title: "Handoffs",
    icon: <KanbanSquare size={14} />,
    content: (
      <>
        <H>Single-winner work</H>
        <P>
          A handoff offers work to a pool (by capability, role or directly).
          Every eligible agent sees it; the first to call handoff_claim wins.
          Without completion within the lease, the claim expires and the work
          returns to the pool.
        </P>
        <H>The kanban</H>
        <P>
          Columns Open → Claimed → Completed / Rejected / Cancelled. The
          operator can cancel Open/Claimed handoffs (confirm-guarded) — they
          leave the pool immediately.
        </P>
        <H>Results in context</H>
        <P>
          Completed cards include the agent response, while rejected cards
          include the rejection reason. Open a card to see the full request,
          acceptance criteria, dependencies and any verification feedback
          alongside that result.
        </P>
      </>
    ),
  },
  {
    id: "meta-harness",
    title: "Meta-harness",
    icon: <Bot size={14} />,
    content: (
      <>
        <H>One conversation surface</H>
        <P>
          Meta-harness combines messages, agent replies, handoff requests and
          terminal handoff results in one chronological chat. Filter by one
          agent or keep the complete team conversation visible.
        </P>
        <H>Compose a turn</H>
        <P>
          Choose <b>Message</b> or <b>Handoff</b>, then <b>Private</b> for the
          agent selected in <b>To</b>, or <b>Broadcast</b> for the workspace.
          Subject is optional. Press Enter to send or Shift+Enter for a new
          line; the message field grows from one to eight lines.
        </P>
        <H>Attach documents</H>
        <P>
          Use the paperclip to attach up to 10 documents (25 MB each). Nexus
          publishes every attachment as an operator-authored artifact in the
          selected workspace before sending the turn, then includes its{" "}
          <code>artifact_id</code> in the message or handoff. The same artifact
          permissions, policies, guardrails, audience rules and managed storage
          used for agent submissions apply. Attachment-only turns are allowed;
          attached files appear inside the chat and can be downloaded there.
        </P>
        <H>Replies and history</H>
        <P>
          Markdown and structured responses are formatted for reading instead
          of shown as raw JSON. New live turns appear at the bottom in
          chronological order. The latest 20 turns load first; at the top,
          choose <b>Load more messages</b> to prepend an older batch without
          losing your reading position.
        </P>
        <H>Read receipts</H>
        <P>
          Outgoing messages show an acknowledgement flag in their footer. It
          stays grey until every target acknowledges the message and turns
          green when all targets are done. Click the indicator to see each
          recipient&apos;s queued, received and acknowledged timestamps and who is
          still pending. Under <b>Settings → Interface behavior</b>, switch the
          receipt display to <b>Timeline receipt messages</b> to restore the
          separate receipt turns.
        </P>
        <H>Handoffs from chat</H>
        <P>
          A broadcast handoff is still single-winner work: the first eligible
          agent to claim it becomes responsible for the result. Terminal
          results return to this conversation and also remain visible on the
          Handoffs board.
        </P>
      </>
    ),
  },
  {
    id: "events",
    title: "Events & Live",
    icon: <Activity size={14} />,
    content: (
      <>
        <H>The live tail</H>
        <P>
          The Events view is the visual successor of `okto-nexus tail`: every
          message, handoff and session writes events to the append-only log,
          and the dashboard receives them via SSE with exact cursor resume —
          a reconnection never loses or duplicates events.
        </P>
        <P>
          The chip at the top shows the connection state: ● Live, Connecting,
          Reconnecting. Any event triggers an incremental graph refresh (no
          page reload).
        </P>
      </>
    ),
  },
  {
    id: "memory",
    title: "Memory",
    icon: <Brain size={14} />,
    content: (
      <>
        <H>Workspace knowledge</H>
        <P>
          Memory is a shared, workspace-scoped store written by agents. Select
          one workspace in the header, then search by text or filter by topic.
          The mode chip tells you whether the result used semantic, lexical or
          recent ordering; semantic results also show a relevance score.
        </P>
        <H>Versions and curation</H>
        <P>
          Turn on <b>Include superseded</b> to inspect replaced entries and use
          the links in the detail panel to follow their lineage. Delete is
          permanent physical curation: it cannot be undone and does not emit a
          bus event.
        </P>
        <H>Feature availability</H>
        <P>
          The navigation entry appears when <code>feature_memory</code> is on.
          Turning it off prevents agent reads and writes but keeps existing
          entries stored.
        </P>
      </>
    ),
  },
  {
    id: "artifacts",
    title: "Artifacts",
    icon: <Files size={14} />,
    content: (
      <>
        <H>Agent deliverables</H>
        <P>
          Artifacts are files or structured text deliberately published by an
          agent with <code>artifact_put</code>. Use the workspace, search and
          type filters, then narrow the results by one or more producing agents
          and a production date interval. Results are loaded in pages of 20.
          Switch between the existing list and an Explorer-style grid whose
          file icons reflect common document, code, image, media, archive and
          spreadsheet types. Open a row or tile to preview text, Markdown,
          HTML, JSON, images or PDFs and download the original payload. Use the
          expand action in the right detail panel for a large modal preview.
        </P>
        <H>Raw and Rich modes</H>
        <P>
          Expanded Markdown, HTML, JSON and CSV previews offer a <b>Rich</b> /{" "}
          <b>Raw</b> toggle. Rich Markdown is rendered, Rich JSON becomes a
          collapsible tree, Rich CSV becomes a scrollable table, and Rich HTML
          preserves embedded CSS and safe document attributes while remaining
          isolated without scripts or external resources. Images render
          directly in both preview sizes without a mode toggle.
        </P>
        <H>Where payloads live</H>
        <P>
          Artifact bytes and free-form metadata are not stored in SQLite. The
          default local adapter copies them below{" "}
          <code>
            ~/.okto_nexus/artifacts/&lt;workspace&gt;/&lt;agent&gt;/&lt;artifact-id&gt;
          </code>
          . SQLite keeps only the minimal catalog and audience fields needed
          for search, quotas and authorization.
        </P>
        <H>Files are imported</H>
        <P>
          When an agent publishes a workspace path, Nexus copies that file into
          managed artifact storage. The artifact therefore remains available if
          the original workspace file is later moved or deleted. A different
          adapter can implement the same storage port without changing the
          application service.
        </P>
      </>
    ),
  },
  {
    id: "workspaces",
    title: "Workspaces",
    icon: <FolderOpen size={14} />,
    content: (
      <>
        <H>Coordination overview</H>
        <P>
          Select a workspace to see its identity, presence roster, recent
          messages and events, open handoffs and most active agent. This screen
          is read-only: workspaces appear as agents coordinate through the bus.
        </P>
        <H>Coordination health</H>
        <P>
          The OK/WARN summary covers unclaimed work, completion time, rejection
          rate, inbox backlog, agent presence and parked deliveries. Switch
          between 1h, 24h and 7d; the cards show the thresholds that caused a
          warning.
        </P>
        <H>Analytics</H>
        <P>
          Use the metric and time-window controls to explore activity by agent.
          Analytics may sample the most recent messages when the workspace is
          large; the header tells you when that happens.
        </P>
      </>
    ),
  },
  {
    id: "registry",
    title: "Registry",
    icon: <Tags size={14} />,
    content: (
      <>
        <H>Controlled vocabulary</H>
        <P>
          Registry is the source of truth for the labels agents may use.{" "}
          <b>Tags</b> define keys and allowed values for agent metadata,
          audience selectors and tag routing. <b>Capabilities</b> define the
          names agents may announce and that capability routing may target.
        </P>
        <H>Register before assigning</H>
        <P>
          Create a tag key or capability here before using it on an agent,
          policy selector or guardrail assignment. Agents can discover the
          current catalogs through <code>tag_list</code> and{" "}
          <code>capability_list</code>.
        </P>
        <H>Safe deletion</H>
        <P>
          A tag, value or capability in use cannot be deleted. The in-use panel
          identifies the agents, selectors or guardrail assignments that must
          be changed first.
        </P>
      </>
    ),
  },
  {
    id: "policies",
    title: "Policies",
    icon: <Shield size={14} />,
    content: (
      <>
        <H>Reusable governance</H>
        <P>
          A policy is a named, versioned package of communication scope and
          governance rules such as denials, quotas and approval requirements.
          Edit its name and description independently from its version history.
        </P>
        <H>Publish, then bind</H>
        <P>
          Publishing appends a new immutable version; previous versions remain
          available for audit. A policy is only staged until you bind it to an
          agent from <b>Agents</b>. Enforcement is driven by that binding and
          applies immediately.
        </P>
        <H>Operate safely</H>
        <P>
          Export or import a policy as JSON to move it between stores. Policies
          that are still bound cannot be deleted, and the in-use panel shows
          every binding to remove. The <b>Recent denials</b> panel explains
          actions rejected by active rules.
        </P>
      </>
    ),
  },
  {
    id: "guardrails",
    title: "Guardrails",
    icon: <ShieldAlert size={14} />,
    content: (
      <>
        <H>1. Groups: choose the agents</H>
        <P>
          Groups are named, reusable lists of explicit agents. Open a group and
          select members from the automatically populated agent list. Use a
          group when the same rule must follow a curated team rather than a
          capability.
        </P>
        <H>2. Guardrails: define the content rule</H>
        <P>
          Choose the content surface and field to inspect. <code>body</code>{" "}
          means the main text content supplied on that surface. Define the match
          as plain text or a regular expression; the regex assistant offers
          examples, describes common tokens and validates the pattern before
          publication.
        </P>
        <H>3. Assignments: decide where it applies</H>
        <P>
          Target all registered agents, an explicit group, or every agent that
          announces a registered capability. Choose the latest active rule or
          pin a version, then select <b>Audit</b> to record matches or{" "}
          <b>Enforce</b> to block matching writes. An assignment can also be
          disabled without deleting it.
        </P>
        <H>Versions and deletion</H>
        <P>
          Rule versions move through draft, active, deprecated and archived
          states. A guardrail or group cannot be deleted while an assignment
          references it; remove the assignment first.
        </P>
      </>
    ),
  },
  {
    id: "communication",
    title: "Communication",
    icon: <MessageSquare size={14} />,
    content: (
      <>
        <H>Reusable styles</H>
        <P>
          Communication presets describe how an agent should respond: tone,
          format, language, verbosity, structure and free-form notes. They
          guide presentation; they do not grant delivery permissions.
        </P>
        <H>Version and bind</H>
        <P>
          Publishing appends an immutable version. Bind a preset to an agent
          from <b>Agents</b>; only that agent receives the style through its{" "}
          <code>whoami</code> response. An agent may use a shared preset or an
          inline style of its own.
        </P>
        <H>Reuse safely</H>
        <P>
          Export and import presets as JSON. A preset that is still bound to an
          agent cannot be deleted; the in-use panel lists the bindings to
          update first.
        </P>
      </>
    ),
  },
  {
    id: "approvals",
    title: "Approvals",
    icon: <CheckSquare size={14} />,
    content: (
      <>
        <H>Human-in-the-loop decisions</H>
        <P>
          Actions intercepted by a <code>require_approval</code> policy wait in{" "}
          <b>Pending approvals</b>. Expand a row to inspect its workspace, target
          and requested payload before deciding.
        </P>
        <H>Approve or reject</H>
        <P>
          Approving executes the original action with its normal effects.
          Rejecting asks for a justification and sends it back to the requester.
          Completed decisions remain visible under <b>Recent decisions</b>.
        </P>
        <H>Feature switch</H>
        <P>
          Turning off <code>feature_hitl</code> stops new interceptions. It
          does not discard existing pending requests, which remain decidable.
        </P>
      </>
    ),
  },
  {
    id: "settings",
    title: "Settings & maintenance",
    icon: <Settings size={14} />,
    content: (
      <>
        <H>Runtime parameters</H>
        <P>
          Every CLI knob (presence and lease TTLs, retention windows, limits,
          trust mode) is editable on the Settings screen and persists across
          restarts. Precedence: CLI &gt; environment variable &gt; value
          saved here &gt; default — a value pinned by a flag shows as
          read-only (cli/env).
        </P>
        <H>Store maintenance</H>
        <ul className="list-disc pl-4 space-y-1 mb-2">
          <Li>
            <b>Prune</b>: applies the retention windows (old events, read
            deliveries, closed sessions). Dry-run it first.
          </Li>
          <Li>
            <b>Reset database</b>: erases the entire operational history
            (with VACUUM). By default agent identities and keys are
            preserved — unchecking the option removes them too and every MCP
            client must reconnect.
          </Li>
        </ul>
      </>
    ),
  },
  {
    id: "cli",
    title: "CLI",
    icon: <TerminalSquare size={14} />,
    content: (
      <>
        <H>Commands</H>
        <Code>{`okto-nexus serve            # HTTP hub + dashboard (port 8202)
okto-nexus serve --port 9000 --host 0.0.0.0
okto-nexus tail --project-root .   # events as NDJSON
okto-nexus admin prune --project-root . --dry-run
okto-nexus admin issue-keys --project-root .
okto-nexus                  # stdio MCP server (V1 mode)`}</Code>
        <H>Binding beyond loopback</H>
        <P>
          With `--host` outside 127.0.0.1, the dashboard and REST start
          requiring an API key (fail-closed on the network). The /mcp
          endpoint requires a key always, on any bind.
        </P>
      </>
    ),
  },
];

export function HelpModal({ onClose }: { onClose: () => void }) {
  const [active, setActive] = useState("quickstart");
  const section = SECTIONS.find((s) => s.id === active) ?? SECTIONS[0];

  return (
    <div
      className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm flex items-center justify-center"
      onClick={onClose}
    >
      <div
        className="relative w-[900px] max-w-[95vw] bg-white dark:bg-surface-900 rounded-xl shadow-2xl h-[85vh] flex flex-col overflow-hidden border border-surface-200/50 dark:border-surface-700/50"
        onClick={(e) => e.stopPropagation()}
        data-testid="help-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="help-modal-title"
      >
        <div className="px-5 py-3 border-b border-surface-200/60 dark:border-surface-700/50 flex items-center justify-between shrink-0">
          <h2
            id="help-modal-title"
            className="font-display font-semibold text-sm text-surface-900 dark:text-surface-100"
          >
            Help — Okto Nexus
          </h2>
          <button
            onClick={onClose}
            className="p-1.5 text-surface-400 hover:text-surface-600 dark:hover:text-surface-300 hover:bg-surface-100 dark:hover:bg-white/10 rounded-lg"
            aria-label="Close help"
          >
            <X size={16} />
          </button>
        </div>
        <div className="flex flex-1 min-h-0">
          <aside
            className="w-48 shrink-0 border-r border-surface-200/60 dark:border-surface-700/50 overflow-y-auto p-2"
            aria-label="Help topics"
          >
            {SECTIONS.map((s) => (
              <button
                key={s.id}
                onClick={() => setActive(s.id)}
                className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-left text-xs transition-colors ${
                  s.id === active
                    ? "bg-accent-100 text-accent-700 dark:bg-accent-900/60 dark:text-accent-200"
                    : "text-surface-600 hover:bg-surface-100 dark:text-surface-400 dark:hover:bg-surface-800"
                }`}
                aria-pressed={s.id === active}
              >
                {s.icon}
                {s.title}
              </button>
            ))}
          </aside>
          <main className="flex-1 overflow-y-auto p-5">{section.content}</main>
        </div>
      </div>
    </div>
  );
}
