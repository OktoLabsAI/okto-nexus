// Help modal - the Pulse HelpPanel pattern: section list on the left,
// scrollable content on the right, Nexus-specific topics.

import { type ReactNode, useState } from "react";
import {
  Activity,
  Bot,
  KanbanSquare,
  KeyRound,
  MessagesSquare,
  Rocket,
  Settings,
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
            <b>Delete</b>: removes the identity for good.
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
        <H>Delivery and audience</H>
        <P>
          Choose <b>Message</b> or <b>Handoff</b>, then choose <b>Private</b>{" "}
          for one selected agent or <b>Broadcast</b> for the workspace. A
          broadcast handoff is single-winner work: the first eligible agent to
          claim it becomes responsible for the result.
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
      >
        <div className="px-5 py-3 border-b border-surface-200/60 dark:border-surface-700/50 flex items-center justify-between shrink-0">
          <h2 className="font-display font-semibold text-sm text-surface-900 dark:text-surface-100">
            Help — Okto Nexus
          </h2>
          <button
            onClick={onClose}
            className="p-1.5 text-surface-400 hover:text-surface-600 dark:hover:text-surface-300 hover:bg-surface-100 dark:hover:bg-white/10 rounded-lg"
          >
            <X size={16} />
          </button>
        </div>
        <div className="flex flex-1 min-h-0">
          <aside className="w-48 shrink-0 border-r border-surface-200/60 dark:border-surface-700/50 overflow-y-auto p-2">
            {SECTIONS.map((s) => (
              <button
                key={s.id}
                onClick={() => setActive(s.id)}
                className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-left text-xs transition-colors ${
                  s.id === active
                    ? "bg-accent-100 text-accent-700 dark:bg-accent-900/60 dark:text-accent-200"
                    : "text-surface-600 hover:bg-surface-100 dark:text-surface-400 dark:hover:bg-surface-800"
                }`}
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
