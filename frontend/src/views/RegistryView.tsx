// Registry (sm_44572557): the central, operator-only catalogs of the
// vocabulary agents may use — tab "Tags" (F1/F3: tag keys + allowed values
// behind agent tags, audience selectors and the "tag" routing strategy) and
// tab "Capabilities" (migration 014: capability names behind agent
// announcements and "capability" routing targets). Both are fail-closed:
// nothing unregistered can be referenced. Usage badges are recomputed
// client-side from the agents list (the same scan the server runs for the
// 409 TAG_IN_USE / CAPABILITY_IN_USE guards); the server stays
// authoritative, so a stale badge at worst shows a delete button that then
// 409s with the exact usage list rendered in the red panel.

import { useEffect, useRef, useState } from "react";
import { AlertTriangle, Plus, X } from "lucide-react";
import {
  api,
  ApiError,
  type AgentRow,
  type CapabilityInUseDetails,
  type CapabilityRow,
  type TagInUseDetails,
  type TagKeyRow,
  type TagUse,
} from "../api";
import { PageContainer } from "../components/PageContainer";
import { useConfirm } from "../components/Confirm";
import { collectUses } from "../tags";

const inputCls =
  "rounded-lg border border-surface-200 dark:border-surface-700 bg-white dark:bg-surface-800 px-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-accent-500/40";

// Agents currently OWNING a capability name (truthy flag in the stored
// flag-map) — the client-side mirror of the server's CAPABILITY_IN_USE scan.
function capabilityOwners(agents: AgentRow[], name: string): string[] {
  return agents
    .filter((agent) => Boolean((agent.capabilities ?? {})[name]))
    .map((agent) => agent.agent_id)
    .sort();
}

function useLabel(use: TagUse, keyName: string, value?: string | null): string {
  if (use.kind === "agent_tags") {
    return value == null ? `tag ${keyName}` : `tag ${keyName}=${value}`;
  }
  return `outbound audience selector uses ${keyName}`;
}

function UsageChip({ uses }: { uses: TagUse[] }) {
  if (uses.length === 0) {
    return (
      <span className="chip bg-surface-200 text-surface-500 dark:bg-surface-700 dark:text-surface-400">
        unused
      </span>
    );
  }
  const agents = uses.filter((u) => u.kind === "agent_tags").length;
  const selectors = uses.filter((u) => u.kind === "comm_scope").length;
  return (
    <span className="chip bg-accent-100 text-accent-700 dark:bg-accent-900/40 dark:text-accent-300">
      used by {agents} agent{agents === 1 ? "" : "s"} · {selectors} selector
      {selectors === 1 ? "" : "s"}
    </span>
  );
}

// The 409 TAG_IN_USE panel: renders the server's normative details payload
// (which agents/selectors still reference the entry, so the operator knows
// exactly what to detach first).
function InUsePanel({
  details,
  onDismiss,
}: {
  details: TagInUseDetails;
  onDismiss: () => void;
}) {
  return (
    <div className="mt-3 rounded-lg border border-red-300 dark:border-red-500/30 bg-red-50 dark:bg-red-900/10 p-3.5">
      <div className="flex items-center gap-2 mb-2">
        <AlertTriangle size={14} className="text-red-500 dark:text-red-400 shrink-0" />
        <p className="text-xs font-semibold text-red-600 dark:text-red-300">
          Cannot delete — TAG_IN_USE (409)
        </p>
      </div>
      <p className="text-xs text-red-600/90 dark:text-red-200/90 mb-2">
        Deleting this entry would silently widen audiences (fail-closed policy
        forbids cascading removal). Remove these usages first:
      </p>
      <ul className="text-xs text-surface-700 dark:text-surface-300 space-y-1 mb-3">
        {details.uses.map((use, i) => (
          <li key={i} className="flex items-center gap-2">
            <span className="w-1 h-1 rounded-full bg-red-400 shrink-0" />
            <span className="font-mono">{use.agent_id}</span>
            <span className="text-surface-500 dark:text-surface-400">
              — {useLabel(use, details.key, details.value)}
            </span>
          </li>
        ))}
      </ul>
      <button className="btn btn-secondary !py-1 text-xs" onClick={onDismiss}>
        Dismiss
      </button>
    </div>
  );
}

// The 409 CAPABILITY_IN_USE panel: the capability twin of InUsePanel — the
// server's normative owner list (agents still announcing the name).
function CapabilityInUsePanel({
  details,
  onDismiss,
}: {
  details: CapabilityInUseDetails;
  onDismiss: () => void;
}) {
  return (
    <div className="mt-3 rounded-lg border border-red-300 dark:border-red-500/30 bg-red-50 dark:bg-red-900/10 p-3.5">
      <div className="flex items-center gap-2 mb-2">
        <AlertTriangle size={14} className="text-red-500 dark:text-red-400 shrink-0" />
        <p className="text-xs font-semibold text-red-600 dark:text-red-300">
          Cannot delete — CAPABILITY_IN_USE (409)
        </p>
      </div>
      <p className="text-xs text-red-600/90 dark:text-red-200/90 mb-2">
        Deleting this name would break agent announcements or guardrail
        assignments. Remove these references first:
      </p>
      <ul className="text-xs text-surface-700 dark:text-surface-300 space-y-1 mb-3">
        {details.uses.map((use, i) => (
          <li key={i} className="flex items-center gap-2">
            <span className="w-1 h-1 rounded-full bg-red-400 shrink-0" />
            <span className="font-mono">
              {use.kind === "capabilities" ? use.agent_id : use.assignment_id}
            </span>
            <span className="text-surface-500 dark:text-surface-400">
              — {use.kind === "capabilities"
                ? `agent announces ${details.capability}`
                : `guardrail assignment targets ${details.capability}`}
            </span>
          </li>
        ))}
      </ul>
      <button className="btn btn-secondary !py-1 text-xs" onClick={onDismiss}>
        Dismiss
      </button>
    </div>
  );
}

function TagsPanel() {
  const { confirm, dialog } = useConfirm();
  const [catalog, setCatalog] = useState<TagKeyRow[]>([]);
  const [agents, setAgents] = useState<AgentRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  // key -> TAG_IN_USE payload of the last refused delete on that card.
  const [inUse, setInUse] = useState<Record<string, TagInUseDetails>>({});
  const [valueDrafts, setValueDrafts] = useState<Record<string, string>>({});
  const [newKey, setNewKey] = useState({ key: "", description: "", values: "" });
  const newKeyRef = useRef<HTMLInputElement>(null);

  const reload = () =>
    Promise.all([api.tags(), api.agents()])
      .then(([t, a]) => {
        setCatalog(t.items);
        setAgents(a.items);
      })
      .catch((exc) => setError((exc as Error).message));

  useEffect(() => {
    reload();
  }, []);

  const runDelete = async (key: string, action: () => Promise<unknown>) => {
    try {
      await action();
      setInUse(({ [key]: _, ...rest }) => rest);
      setError(null);
      await reload();
    } catch (exc) {
      if (exc instanceof ApiError && exc.code === "TAG_IN_USE") {
        setInUse((cur) => ({ ...cur, [key]: exc.details as TagInUseDetails }));
      } else {
        setError((exc as Error).message);
      }
    }
  };

  const addValue = async (key: string) => {
    const value = (valueDrafts[key] ?? "").trim();
    if (!value) return;
    try {
      await api.createTagValue(key, { value });
      setValueDrafts((cur) => ({ ...cur, [key]: "" }));
      setError(null);
      await reload();
    } catch (exc) {
      setError((exc as Error).message);
    }
  };

  const registerKey = async () => {
    const key = newKey.key.trim();
    if (!key) return;
    try {
      await api.createTagKey({
        key,
        description: newKey.description.trim() || undefined,
      });
      // Initial values are best-effort follow-ups: the key exists either way,
      // and a bad token fails loudly below without rolling the key back.
      for (const value of newKey.values.split(",").map((v) => v.trim())) {
        if (value) await api.createTagValue(key, { value });
      }
      setNewKey({ key: "", description: "", values: "" });
      setError(null);
      await reload();
    } catch (exc) {
      setError((exc as Error).message);
      await reload();
    }
  };

  const totalValues = catalog.reduce((n, k) => n + k.values.length, 0);

  return (
    <div data-testid="tags-panel">
      {dialog}
      <div className="flex items-center gap-2 mb-5">
        <span className="chip bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300">
          Operator-only
        </span>
        <span className="chip bg-surface-200 text-surface-600 dark:bg-surface-700 dark:text-surface-300">
          {catalog.length} key{catalog.length === 1 ? "" : "s"} · {totalValues}{" "}
          value{totalValues === 1 ? "" : "s"}
        </span>
        <button
          className="btn btn-primary ml-auto shrink-0"
          onClick={() => newKeyRef.current?.focus()}
          data-testid="new-tag-key"
        >
          <Plus size={14} /> New key
        </button>
      </div>

      {error && <p className="mb-3 text-xs text-red-500">{error}</p>}

      {/* One card per registered key */}
      <div className="space-y-4">
        {catalog.map((entry) => {
          const keyUses = collectUses(agents, entry.key);
          const blocked = inUse[entry.key];
          return (
            <section
              key={entry.key}
              className={`panel p-4 ${
                blocked ? "border-red-300 dark:border-red-500/30" : ""
              }`}
              data-testid={`tag-key-${entry.key}`}
            >
              <div className="flex items-center gap-3 mb-1">
                <h2 className="text-sm font-semibold font-mono tracking-wide text-surface-900 dark:text-surface-100">
                  {entry.key}
                </h2>
                <UsageChip uses={keyUses} />
                <button
                  className={`ml-auto text-xs ${
                    keyUses.length
                      ? "text-surface-400 dark:text-surface-600 cursor-not-allowed"
                      : "text-surface-500 hover:text-red-500 dark:text-surface-400"
                  }`}
                  disabled={keyUses.length > 0}
                  title={
                    keyUses.length
                      ? "Key is in use — remove all usages first"
                      : "Delete this key and its values"
                  }
                  onClick={() =>
                    confirm({
                      title: "Delete tag key?",
                      body: (
                        <span>
                          <b className="font-mono">{entry.key}</b> and its{" "}
                          {entry.values.length} value
                          {entry.values.length === 1 ? "" : "s"} will be removed
                          from the catalog.
                        </span>
                      ),
                      onConfirm: () =>
                        runDelete(entry.key, () => api.deleteTagKey(entry.key)),
                    })
                  }
                  data-testid={`delete-key-${entry.key}`}
                >
                  Delete key
                </button>
              </div>
              {entry.description && (
                <p className="text-xs text-surface-500 dark:text-surface-400 mb-3">
                  {entry.description}
                </p>
              )}
              <div className="flex flex-wrap items-center gap-1.5 mt-2">
                {entry.values.map((v) => {
                  const valueUses = collectUses(agents, entry.key, v.value);
                  return (
                    <span
                      key={v.value}
                      className="inline-flex items-center gap-1.5 text-xs px-2 py-1 rounded-md border border-surface-200 dark:border-surface-700 bg-surface-50 dark:bg-surface-900 font-mono text-surface-700 dark:text-surface-200"
                      title={v.description ?? undefined}
                    >
                      {v.value}
                      <span className="text-surface-400 dark:text-surface-500 font-sans">
                        · {valueUses.length} use{valueUses.length === 1 ? "" : "s"}
                      </span>
                      <button
                        className={
                          valueUses.length
                            ? "text-surface-300 dark:text-surface-600 cursor-not-allowed"
                            : "text-surface-400 hover:text-red-500"
                        }
                        disabled={valueUses.length > 0}
                        title={
                          valueUses.length
                            ? "Value is in use — remove all usages first"
                            : "Delete this value"
                        }
                        onClick={() =>
                          confirm({
                            title: "Delete tag value?",
                            body: (
                              <span>
                                <b className="font-mono">
                                  {entry.key}={v.value}
                                </b>{" "}
                                will be removed from the catalog.
                              </span>
                            ),
                            onConfirm: () =>
                              runDelete(entry.key, () =>
                                api.deleteTagValue(entry.key, v.value),
                              ),
                          })
                        }
                      >
                        <X size={11} />
                      </button>
                    </span>
                  );
                })}
                <span className="inline-flex items-center gap-1">
                  <input
                    placeholder="new value"
                    value={valueDrafts[entry.key] ?? ""}
                    onChange={(e) =>
                      setValueDrafts((cur) => ({
                        ...cur,
                        [entry.key]: e.target.value,
                      }))
                    }
                    onKeyDown={(e) => e.key === "Enter" && addValue(entry.key)}
                    className={`${inputCls} w-28 font-mono`}
                    data-testid={`new-value-${entry.key}`}
                  />
                  <button
                    className="btn btn-secondary !py-1 text-xs"
                    onClick={() => addValue(entry.key)}
                    disabled={!(valueDrafts[entry.key] ?? "").trim()}
                  >
                    Add
                  </button>
                </span>
              </div>
              {blocked && (
                <InUsePanel
                  details={blocked}
                  onDismiss={() =>
                    setInUse(({ [entry.key]: _, ...rest }) => rest)
                  }
                />
              )}
            </section>
          );
        })}
        {catalog.length === 0 && (
          <p className="text-xs text-surface-400 dark:text-surface-500">
            No tag keys registered yet — register the first one below.
          </p>
        )}
      </div>

      {/* Register a new key */}
      <section
        className="mt-5 rounded-xl border border-dashed border-surface-300 dark:border-surface-700 p-4"
        data-testid="new-key-form"
      >
        <h2 className="text-sm font-semibold text-surface-700 dark:text-surface-300 mb-3">
          Register a new key
        </h2>
        <div className="flex flex-wrap items-end gap-3">
          <label className="block">
            <span className="text-[11px] uppercase tracking-wide text-surface-500 dark:text-surface-400">
              Key
            </span>
            <input
              ref={newKeyRef}
              placeholder="e.g. TIER"
              value={newKey.key}
              onChange={(e) => setNewKey({ ...newKey, key: e.target.value })}
              className={`${inputCls} mt-1 block w-36 font-mono`}
              data-testid="new-key-name"
            />
          </label>
          <label className="block flex-1 min-w-48">
            <span className="text-[11px] uppercase tracking-wide text-surface-500 dark:text-surface-400">
              Description (optional)
            </span>
            <input
              placeholder="What this key classifies"
              value={newKey.description}
              onChange={(e) =>
                setNewKey({ ...newKey, description: e.target.value })
              }
              className={`${inputCls} mt-1 block w-full`}
            />
          </label>
          <label className="block flex-1 min-w-48">
            <span className="text-[11px] uppercase tracking-wide text-surface-500 dark:text-surface-400">
              Initial values (comma-separated)
            </span>
            <input
              placeholder="GOLD, SILVER"
              value={newKey.values}
              onChange={(e) => setNewKey({ ...newKey, values: e.target.value })}
              className={`${inputCls} mt-1 block w-full font-mono`}
            />
          </label>
          <button
            className="btn btn-primary"
            onClick={registerKey}
            disabled={!newKey.key.trim()}
            data-testid="register-key"
          >
            Register
          </button>
        </div>
        <p className="text-[11px] text-surface-400 dark:text-surface-500 mt-3">
          Keys and values are exact-match and case-sensitive. Agents discover
          this catalog read-only via the{" "}
          <code className="font-mono">tag_list</code> MCP tool.
        </p>
      </section>
    </div>
  );
}

function CapabilitiesPanel() {
  const { confirm, dialog } = useConfirm();
  const [catalog, setCatalog] = useState<CapabilityRow[]>([]);
  const [agents, setAgents] = useState<AgentRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  // name -> CAPABILITY_IN_USE payload of the last refused delete on that row.
  const [inUse, setInUse] = useState<Record<string, CapabilityInUseDetails>>({});
  const [draft, setDraft] = useState({ name: "", description: "" });
  const nameRef = useRef<HTMLInputElement>(null);

  const reload = () =>
    Promise.all([api.capabilities(), api.agents()])
      .then(([c, a]) => {
        setCatalog(c.items);
        setAgents(a.items);
      })
      .catch((exc) => setError((exc as Error).message));

  useEffect(() => {
    reload();
  }, []);

  const remove = async (name: string) => {
    try {
      await api.deleteCapability(name);
      setInUse(({ [name]: _, ...rest }) => rest);
      setError(null);
      await reload();
    } catch (exc) {
      if (exc instanceof ApiError && exc.code === "CAPABILITY_IN_USE") {
        setInUse((cur) => ({
          ...cur,
          [name]: exc.details as CapabilityInUseDetails,
        }));
      } else {
        setError((exc as Error).message);
      }
    }
  };

  const register = async () => {
    const name = draft.name.trim();
    if (!name) return;
    try {
      await api.createCapability({
        name,
        description: draft.description.trim() || undefined,
      });
      setDraft({ name: "", description: "" });
      setError(null);
      await reload();
    } catch (exc) {
      setError((exc as Error).message);
    }
  };

  return (
    <div data-testid="capabilities-panel">
      {dialog}
      <div className="flex items-center gap-2 mb-5">
        <span className="chip bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300">
          Operator-only
        </span>
        <span className="chip bg-surface-200 text-surface-600 dark:bg-surface-700 dark:text-surface-300">
          {catalog.length} capabilit{catalog.length === 1 ? "y" : "ies"}
        </span>
        <button
          className="btn btn-primary ml-auto shrink-0"
          onClick={() => nameRef.current?.focus()}
          data-testid="new-capability"
        >
          <Plus size={14} /> New capability
        </button>
      </div>

      {error && <p className="mb-3 text-xs text-red-500">{error}</p>}

      {/* One row per registered capability */}
      <div className="space-y-3">
        {catalog.map((entry) => {
          const owners = capabilityOwners(agents, entry.name);
          const blocked = inUse[entry.name];
          return (
            <section
              key={entry.name}
              className={`panel p-4 ${
                blocked ? "border-red-300 dark:border-red-500/30" : ""
              }`}
              data-testid={`capability-${entry.name}`}
            >
              <div className="flex items-center gap-3">
                <h2 className="text-sm font-semibold font-mono tracking-wide text-surface-900 dark:text-surface-100">
                  {entry.name}
                </h2>
                {owners.length === 0 ? (
                  <span className="chip bg-surface-200 text-surface-500 dark:bg-surface-700 dark:text-surface-400">
                    unused
                  </span>
                ) : (
                  <span
                    className="chip bg-accent-100 text-accent-700 dark:bg-accent-900/40 dark:text-accent-300"
                    title={owners.join(", ")}
                  >
                    owned by {owners.length} agent{owners.length === 1 ? "" : "s"}
                  </span>
                )}
                <button
                  className={`ml-auto text-xs ${
                    owners.length
                      ? "text-surface-400 dark:text-surface-600 cursor-not-allowed"
                      : "text-surface-500 hover:text-red-500 dark:text-surface-400"
                  }`}
                  disabled={owners.length > 0}
                  title={
                    owners.length
                      ? "Capability is owned by agents — remove it from them first"
                      : "Delete this capability from the catalog"
                  }
                  onClick={() =>
                    confirm({
                      title: "Delete capability?",
                      body: (
                        <span>
                          <b className="font-mono">{entry.name}</b> will be
                          removed from the catalog. New announcements and{" "}
                          <code className="font-mono">capability</code> targets
                          referencing it will be rejected.
                        </span>
                      ),
                      onConfirm: () => remove(entry.name),
                    })
                  }
                  data-testid={`delete-capability-${entry.name}`}
                >
                  Delete
                </button>
              </div>
              {entry.description && (
                <p className="text-xs text-surface-500 dark:text-surface-400 mt-1">
                  {entry.description}
                </p>
              )}
              {owners.length > 0 && (
                <p className="text-[11px] font-mono text-surface-400 dark:text-surface-500 mt-2 truncate">
                  {owners.slice(0, 8).join(", ")}
                  {owners.length > 8 ? ", …" : ""}
                </p>
              )}
              {blocked && (
                <CapabilityInUsePanel
                  details={blocked}
                  onDismiss={() =>
                    setInUse(({ [entry.name]: _, ...rest }) => rest)
                  }
                />
              )}
            </section>
          );
        })}
        {catalog.length === 0 && (
          <p className="text-xs text-surface-400 dark:text-surface-500">
            No capabilities registered yet — register the first one below.
          </p>
        )}
      </div>

      {/* Register a new capability */}
      <section
        className="mt-5 rounded-xl border border-dashed border-surface-300 dark:border-surface-700 p-4"
        data-testid="new-capability-form"
      >
        <h2 className="text-sm font-semibold text-surface-700 dark:text-surface-300 mb-3">
          Register a new capability
        </h2>
        <div className="flex flex-wrap items-end gap-3">
          <label className="block">
            <span className="text-[11px] uppercase tracking-wide text-surface-500 dark:text-surface-400">
              Name
            </span>
            <input
              ref={nameRef}
              placeholder="e.g. ocr"
              value={draft.name}
              onChange={(e) => setDraft({ ...draft, name: e.target.value })}
              onKeyDown={(e) => e.key === "Enter" && register()}
              className={`${inputCls} mt-1 block w-40 font-mono`}
              data-testid="new-capability-name"
            />
          </label>
          <label className="block flex-1 min-w-48">
            <span className="text-[11px] uppercase tracking-wide text-surface-500 dark:text-surface-400">
              Description (optional)
            </span>
            <input
              placeholder="What agents with this capability can do"
              value={draft.description}
              onChange={(e) =>
                setDraft({ ...draft, description: e.target.value })
              }
              className={`${inputCls} mt-1 block w-full`}
            />
          </label>
          <button
            className="btn btn-primary"
            onClick={register}
            disabled={!draft.name.trim()}
            data-testid="register-capability"
          >
            Register
          </button>
        </div>
        <p className="text-[11px] text-surface-400 dark:text-surface-500 mt-3">
          Names are exact-match and case-sensitive. Agents discover this
          catalog (with descriptions and owners) via the{" "}
          <code className="font-mono">capability_list</code> MCP tool;
          announcing or targeting an unregistered name is rejected
          (fail-closed).
        </p>
      </section>
    </div>
  );
}

export function RegistryView() {
  const [tab, setTab] = useState<"tags" | "capabilities">("tags");

  return (
    <PageContainer width="readable" scroll="y" testId="registry-view">
      {/* Header */}
      <div className="mb-3">
        <h1 className="text-lg font-display font-semibold text-surface-900 dark:text-surface-100">
          Registry
        </h1>
        <p className="text-xs text-surface-500 dark:text-surface-400 mt-1">
          Central catalogs of the vocabulary agents may use. Tags back agent
          labels, audience selectors and <code className="font-mono">tag</code>{" "}
          routing; capabilities back agent announcements and{" "}
          <code className="font-mono">capability</code> routing. Both are
          fail-closed: only entries registered here can be referenced.
        </p>
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-1 mb-4">
        {(
          [
            ["tags", "Tags"],
            ["capabilities", "Capabilities"],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={`px-3 py-1.5 rounded-lg font-display font-semibold text-sm transition-colors ${
              tab === id
                ? "bg-accent-100 text-accent-700 dark:bg-accent-900/60 dark:text-accent-200"
                : "text-surface-500 hover:text-surface-800 dark:hover:text-surface-200"
            }`}
            data-testid={`registry-tab-${id}`}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "tags" ? <TagsPanel /> : <CapabilitiesPanel />}
    </PageContainer>
  );
}
