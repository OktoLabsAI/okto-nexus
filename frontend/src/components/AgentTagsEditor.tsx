// Agent Tags + Audience (outbound/inbound) editors (F1+F2+F3 / sm_188b58c0).
// All operator-only and STRICTLY catalog-driven: every key/value is PICKED
// from the central Tag Registry via dropdown pickers — no free-form input,
// so the fail-closed existence gate on PATCH can only trip on registry
// races. The reusable audience primitives (Picker, KeyRow, the Simple/
// Expressions leg editor, the leg helpers) now live in ./AudienceEditor so the
// policy catalog can reuse them; this module composes them for the AGENT edit
// flow (tags + both audience legs, saved as one full overwrite via
// updateAgent). Saving is a full overwrite: empty tags -> null reset, no
// audience conditions on either leg -> comm_scope null (unrestricted).

import { useEffect, useMemo, useState } from "react";
import { Eye, Info, X } from "lucide-react";
import {
  api,
  type AgentGlobalBinding,
  type AgentRow,
  type CommScope,
  type PolicyRecord,
  type PolicyRule,
  type TagKeyRow,
  type TagMap,
  type TagSelector,
} from "../api";
import {
  inboundSelector,
  normalizeTagMap,
  outboundSelector,
  selectorMatches,
} from "../tags";
import {
  AudienceLegEditor,
  KeyRow,
  OperatorOnlyBadge,
  Picker,
  initLeg,
  legIncomplete,
  legSelector,
  type LegState,
} from "./AudienceEditor";
import { GovernanceRulesEditor } from "./GovernanceRulesEditor";

// Re-exported so CapabilityPicker / RegistryView keep importing Picker from
// here (its original home) even though it now lives in ./AudienceEditor.
export { Picker };

export function AgentTagsEditor({
  agent,
  catalog,
  agents,
  onSaved,
  onClose,
}: {
  agent: AgentRow;
  catalog: TagKeyRow[];
  agents: AgentRow[];
  onSaved: () => Promise<void> | void;
  onClose: () => void;
}) {
  const [tags, setTags] = useState<TagMap>(() => normalizeTagMap(agent.tags));
  const [outbound, setOutbound] = useState<LegState>(() =>
    initLeg(outboundSelector(agent)),
  );
  const [inbound, setInbound] = useState<LegState>(() =>
    initLeg(inboundSelector(agent)),
  );
  // Attachable policies (spec 80624c1a): the agent's global references + its
  // inline governance, read from the binding surface so the editor never blindly
  // overwrites. The audience above is ALSO the inline policy's audience — the
  // save writes it to both comm_scope and the inline binding (Option A).
  const [globals, setGlobals] = useState<AgentGlobalBinding[]>([]);
  const [inlineGov, setInlineGov] = useState<PolicyRule[]>([]);
  const [policyCatalog, setPolicyCatalog] = useState<PolicyRecord[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api
      .policies()
      .then(({ items }) => setPolicyCatalog(items))
      .catch(() => undefined);
    api
      .agentPolicies(agent.agent_id)
      .then((bindings) => {
        setGlobals(bindings.globals);
        setInlineGov(bindings.inline?.governance ?? []);
      })
      .catch(() => undefined);
  }, [agent.agent_id]);

  const byKey = useMemo(
    () => new Map(catalog.map((entry) => [entry.key, entry])),
    [catalog],
  );

  const policyById = useMemo(
    () => new Map(policyCatalog.map((p) => [p.policy_id, p])),
    [policyCatalog],
  );

  const attachablePolicyItems = policyCatalog
    .filter((p) => !globals.some((g) => g.policy_id === p.policy_id))
    .map((p) => ({
      id: p.policy_id,
      label: (
        <span className="flex justify-between gap-2">
          <span className="font-mono truncate">{p.name}</span>
          <span className="text-surface-400 dark:text-surface-500">
            {p.latest_version === 0 ? "no versions" : `@v${p.latest_version}`}
          </span>
        </span>
      ),
    }));

  const addGlobal = (policyId: string) =>
    setGlobals((cur) => [...cur, { policy_id: policyId, mode: "latest" }]);

  const removeGlobal = (index: number) =>
    setGlobals((cur) => cur.filter((_, i) => i !== index));

  const setGlobalMode = (index: number, mode: "latest" | "pinned") =>
    setGlobals((cur) =>
      cur.map((g, i) => {
        if (i !== index) return g;
        if (mode === "pinned") {
          const latest = policyById.get(g.policy_id)?.latest_version ?? 0;
          return {
            policy_id: g.policy_id,
            mode,
            pinned_version: g.pinned_version ?? latest ?? 1,
          };
        }
        return { policy_id: g.policy_id, mode: "latest" };
      }),
    );

  const setGlobalPinned = (index: number, version: number) =>
    setGlobals((cur) =>
      cur.map((g, i) => (i === index ? { ...g, pinned_version: version } : g)),
    );

  const keyPickerItems = (used: TagMap) =>
    catalog.map((entry) => ({
      id: entry.key,
      label: (
        <span className="flex justify-between gap-2">
          <span className="font-mono">{entry.key}</span>
          <span className="text-surface-400 dark:text-surface-500">
            {entry.key in used
              ? "in use"
              : `${entry.values.length} value${entry.values.length === 1 ? "" : "s"}`}
          </span>
        </span>
      ),
      disabled: entry.key in used,
    }));

  const patchMap = (
    set: (fn: (cur: TagMap) => TagMap) => void,
    key: string,
    mutate: (values: string[]) => string[] | null,
    options: { keepEmpty?: boolean } = {},
  ) =>
    set((cur) => {
      const next = { ...cur };
      const mutated = mutate(next[key] ?? []);
      if (mutated === null || (!options.keepEmpty && mutated.length === 0)) {
        delete next[key];
      } else {
        next[key] = mutated;
      }
      return next;
    });

  const setTagsMap = (fn: (cur: TagMap) => TagMap) => setTags(fn);

  const outboundEffective = legSelector(outbound);
  const inboundEffective = legSelector(inbound);
  const tagsIncomplete = Object.values(tags).some((values) => values.length === 0);
  const incomplete =
    tagsIncomplete || legIncomplete(outbound) || legIncomplete(inbound);
  const outboundPreview = useMemo(() => {
    if (!outboundEffective) return null;
    const matched = agents.filter((a) =>
      selectorMatches(outboundEffective, a.tags),
    );
    return { matched, total: agents.length };
  }, [agents, outboundEffective]);
  const inboundPreview = useMemo(() => {
    if (!inboundEffective) return null;
    const matched = agents.filter((a) =>
      selectorMatches(inboundEffective, a.tags),
    );
    return { matched, total: agents.length };
  }, [agents, inboundEffective]);

  const save = async () => {
    setSaving(true);
    try {
      const scope: CommScope = {};
      if (outboundEffective) scope.outbound = outboundEffective;
      if (inboundEffective) scope.inbound = inboundEffective;
      const commScope: CommScope | null =
        outboundEffective || inboundEffective ? scope : null;
      // (1) Legacy comm_scope + tags. comm_scope drives the message-fanout
      // audience gate (which still reads the agent field, not the bindings).
      await api.updateAgent(agent.agent_id, {
        tags: Object.keys(tags).length ? tags : null,
        comm_scope: commScope,
      });
      // (2) Unified bindings: the SAME audience embedded as the inline policy
      // (which drives handoff/artifact enforcement) + inline governance + the
      // attached globals. Dual-write keeps comm_scope and the inline audience in
      // lockstep, so both enforcement paths agree (Option A, spec 80624c1a).
      const inline =
        commScope || inlineGov.length
          ? { audience: commScope ?? undefined, governance: inlineGov }
          : undefined;
      await api.setAgentPolicies(agent.agent_id, { globals, inline });
      setError(null);
      await onSaved();
      onClose();
    } catch (exc) {
      setError((exc as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const tagChip =
    "inline-flex items-center gap-1 text-xs px-2 py-1 rounded-md bg-accent-100 text-accent-700 dark:bg-accent-900/40 dark:text-accent-300 border border-accent-200 dark:border-accent-800/50 font-mono";
  const audienceChip =
    "inline-flex items-center gap-1 text-xs px-2 py-1 rounded-md bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800/50 font-mono";

  return (
    <div
      className="space-y-4 rounded-xl border border-surface-200 dark:border-surface-700 p-3 animate-slide-up"
      data-testid={`tags-panel-${agent.agent_id}`}
    >
      {/* Tags */}
      <section>
        <div className="flex items-center gap-2 mb-1">
          <h3 className="text-xs font-semibold tracking-wide text-surface-700 dark:text-surface-200">
            Tags
          </h3>
          <OperatorOnlyBadge />
        </div>
        <p className="text-xs text-surface-500 dark:text-surface-400 mb-3">
          Key/value labels used by audience selectors and the{" "}
          <code className="font-mono">tag</code> routing strategy. Agents cannot
          edit their own tags. Keys and values come from the central Tag
          Registry — unregistered entries are rejected (fail-closed).
        </p>
        <div className="space-y-2">
          {Object.entries(tags).map(([key, values]) => (
            <KeyRow
              key={key}
              keyName={key}
              values={values}
              registered={byKey.get(key)}
              chipCls={tagChip}
              onAdd={(v) => patchMap(setTagsMap, key, (cur) => [...cur, v])}
              onRemoveValue={(v) =>
                patchMap(setTagsMap, key, (cur) => cur.filter((x) => x !== v))
              }
              onRemoveKey={() => patchMap(setTagsMap, key, () => null)}
            />
          ))}
          <Picker
            trigger="+ Add key"
            header="Registered keys"
            items={keyPickerItems(tags)}
            footer="Only registered keys can be assigned. Manage them in the Tag Registry."
            filterable
            onPick={(key) =>
              patchMap(setTagsMap, key, (cur) => cur, { keepEmpty: true })
            }
          />
        </div>
      </section>

      {/* Audience (outbound) — who THIS agent can reach */}
      <AudienceLegEditor
        title="Audience — outbound"
        blurb={
          <>
            Restricts who this agent can reach with direct messages,
            broadcasts and handoffs.{" "}
            <span className="text-surface-600 dark:text-surface-300">
              No conditions = no restriction.
            </span>{" "}
            Simple mode: AND across keys, OR across values. Expressions mode
            adds In / NotIn / Exists / DoesNotExist (ANDed). Conditions are
            built from Tag Registry entries only; values match hierarchically
            by <code className="font-mono">/</code> segment (ENG covers
            ENG/BACKEND).
          </>
        }
        leg={outbound}
        setLeg={(fn) => setOutbound(fn)}
        byKey={byKey}
        catalog={catalog}
        simpleKeyItems={keyPickerItems(
          outbound.mode === "simple" ? outbound.map : {},
        )}
        chipCls={audienceChip}
        preview={
          outboundPreview && (
            <div className="mt-3 flex items-start gap-2 rounded-lg border border-accent-200 dark:border-accent-800/50 bg-accent-50/50 dark:bg-accent-900/10 px-3 py-2.5">
              <Eye size={14} className="text-accent-500 dark:text-accent-400 mt-0.5 shrink-0" />
              <p className="text-xs text-surface-600 dark:text-surface-300">
                This agent can currently reach{" "}
                <span className="font-semibold">
                  {outboundPreview.matched.length} of {outboundPreview.total}
                </span>{" "}
                registered agents
                {outboundPreview.matched.length > 0 && (
                  <>
                    :{" "}
                    <span className="font-mono">
                      {outboundPreview.matched
                        .slice(0, 6)
                        .map((a) => a.agent_id)
                        .join(", ")}
                      {outboundPreview.matched.length > 6 ? ", …" : ""}
                    </span>
                  </>
                )}
                . Each target's own inbound filter still applies.
              </p>
            </div>
          )
        }
      >
        {/* allowed_peers is gone (informational only) */}
        <div className="mt-3 flex items-start gap-2 rounded-lg border border-surface-200 dark:border-surface-700 bg-surface-50/60 dark:bg-surface-900/40 px-3 py-2.5">
          <Info size={14} className="text-surface-400 dark:text-surface-500 mt-0.5 shrink-0" />
          <p className="text-xs text-surface-500 dark:text-surface-400">
            The legacy <code className="font-mono">allowed_peers</code>{" "}
            allowlist was removed in this release; stored values are ignored.
            Recreate that policy as an audience selector above.
          </p>
        </div>
      </AudienceLegEditor>

      {/* Audience (inbound) — who can reach THIS agent */}
      <AudienceLegEditor
        title="Audience — inbound"
        blurb={
          <>
            Restricts who can reach this agent: senders whose tags miss the
            filter are blocked (direct sends) or silently dropped (group
            fan-outs), and this agent stops seeing them in discovery and the
            event stream.{" "}
            <span className="text-surface-600 dark:text-surface-300">
              No conditions = anyone may reach it.
            </span>{" "}
            Simple mode: AND across keys, OR across values. Expressions mode
            adds In / NotIn / Exists / DoesNotExist (ANDed). Conditions are
            built from Tag Registry entries only.
          </>
        }
        leg={inbound}
        setLeg={(fn) => setInbound(fn)}
        byKey={byKey}
        catalog={catalog}
        simpleKeyItems={keyPickerItems(
          inbound.mode === "simple" ? inbound.map : {},
        )}
        chipCls={audienceChip}
        preview={
          inboundPreview && (
            <div className="mt-3 flex items-start gap-2 rounded-lg border border-accent-200 dark:border-accent-800/50 bg-accent-50/50 dark:bg-accent-900/10 px-3 py-2.5">
              <Eye size={14} className="text-accent-500 dark:text-accent-400 mt-0.5 shrink-0" />
              <p className="text-xs text-surface-600 dark:text-surface-300">
                <span className="font-semibold">
                  {inboundPreview.matched.length} of {inboundPreview.total}
                </span>{" "}
                registered agents currently pass this filter and may reach
                this agent
                {inboundPreview.matched.length > 0 && (
                  <>
                    :{" "}
                    <span className="font-mono">
                      {inboundPreview.matched
                        .slice(0, 6)
                        .map((a) => a.agent_id)
                        .join(", ")}
                      {inboundPreview.matched.length > 6 ? ", …" : ""}
                    </span>
                  </>
                )}
                . Each sender's own outbound scope still applies on top.
              </p>
            </div>
          )
        }
      />

      {/* Attached policies (spec 80624c1a): reusable, versioned GLOBAL
          references + this agent's own INLINE governance. Inline and global
          policies have the SAME force and vocabulary — they differ only in
          placement/registration and reuse — and compose by intersection
          (AND, fail-safe): attaching can only NARROW, never widen. The audience
          above is this agent's inline audience (saved to both stores). */}
      <section className="pt-3 border-t border-surface-200/60 dark:border-surface-700/50">
        <div className="flex items-center gap-2 mb-1">
          <h3 className="text-xs font-semibold tracking-wide text-surface-700 dark:text-surface-200">
            Attached policies
          </h3>
          <OperatorOnlyBadge />
        </div>
        <p className="text-xs text-surface-500 dark:text-surface-400 mb-3">
          Global policies are named, versioned and reusable across agents; the
          inline policy is embedded on this agent alone. Both carry audience +
          governance with identical force and compose by intersection — a policy
          only ever narrows what this agent can do.
        </p>

        {/* Global bindings */}
        <div className="space-y-2">
          {globals.map((g, index) => {
            const rec = policyById.get(g.policy_id);
            const latest = rec?.latest_version ?? 0;
            return (
              <div
                key={`${g.policy_id}-${index}`}
                className="flex items-center gap-2 rounded-lg border border-surface-200 dark:border-surface-700 bg-surface-50/60 dark:bg-surface-900/60 px-3 py-2"
                data-testid={`global-binding-${g.policy_id}`}
              >
                <span
                  className="text-xs font-mono text-surface-700 dark:text-surface-200 truncate"
                  title={g.policy_id}
                >
                  {rec?.name ?? g.policy_id}
                </span>
                <select
                  value={g.mode}
                  onChange={(e) =>
                    setGlobalMode(index, e.target.value as "latest" | "pinned")
                  }
                  className="ml-auto shrink-0 text-xs font-mono rounded-md border border-surface-300 dark:border-surface-600 bg-white dark:bg-surface-800 px-1.5 py-1 text-surface-700 dark:text-surface-200"
                  title="latest follows the newest version; pinned freezes on one"
                >
                  <option value="latest">latest</option>
                  <option value="pinned" disabled={latest === 0}>
                    pinned
                  </option>
                </select>
                {g.mode === "pinned" ? (
                  <select
                    value={g.pinned_version ?? latest}
                    onChange={(e) =>
                      setGlobalPinned(index, Number(e.target.value))
                    }
                    className="shrink-0 text-xs font-mono rounded-md border border-surface-300 dark:border-surface-600 bg-white dark:bg-surface-800 px-1.5 py-1 text-surface-700 dark:text-surface-200"
                  >
                    {Array.from({ length: latest }, (_, i) => latest - i).map(
                      (v) => (
                        <option key={v} value={v}>
                          @v{v}
                        </option>
                      ),
                    )}
                  </select>
                ) : (
                  <span
                    className={`chip shrink-0 ${
                      latest === 0
                        ? "bg-surface-200 text-surface-500 dark:bg-surface-700 dark:text-surface-400"
                        : "bg-accent-100 text-accent-700 dark:bg-accent-900/40 dark:text-accent-300 font-mono"
                    }`}
                  >
                    {latest === 0 ? "no versions" : `@v${latest}`}
                  </span>
                )}
                <button
                  className="shrink-0 text-surface-400 hover:text-red-500"
                  onClick={() => removeGlobal(index)}
                  title="Detach this policy"
                  data-testid={`detach-global-${g.policy_id}`}
                >
                  <X size={13} />
                </button>
              </div>
            );
          })}
          <Picker
            trigger="+ Attach a global policy"
            header="Global policies"
            items={attachablePolicyItems}
            footer="Manage the catalog in the Policies screen."
            filterable
            onPick={addGlobal}
          />
          {policyCatalog.length === 0 && (
            <p className="text-xs text-surface-400 dark:text-surface-500">
              No global policies exist yet — create them in the Policies screen.
            </p>
          )}
        </div>

        {/* Inline governance — the SAME editor a global policy version uses */}
        <div className="mt-4">
          <span className="text-[11px] uppercase tracking-wide text-surface-500 dark:text-surface-400">
            Inline governance rules
          </span>
          <p className="text-xs text-surface-500 dark:text-surface-400 mt-0.5">
            Deny/quota rules embedded on this agent — same vocabulary and force
            as a global policy's rules, just not reusable.
          </p>
          <GovernanceRulesEditor
            rules={inlineGov}
            onChange={setInlineGov}
            testId={`inline-gov-${agent.agent_id}`}
          />
        </div>
      </section>

      {error && <p className="text-xs text-red-500">{error}</p>}
      <div className="flex items-center gap-2">
        <button
          className="btn btn-primary"
          onClick={save}
          disabled={saving || incomplete}
          title={
            incomplete
              ? tagsIncomplete
                ? "Every assigned tag key needs at least one value"
                : "Every In/NotIn expression needs at least one value"
              : undefined
          }
          data-testid={`save-tags-${agent.agent_id}`}
        >
          Save changes
        </button>
        <button className="btn btn-secondary" onClick={onClose}>
          Cancel
        </button>
        <span className="text-[10px] text-surface-400 dark:text-surface-500">
          Saving overwrites tags, audience and attached policies; clearing
          everything resets the agent to unrestricted and unbound.
        </span>
      </div>
    </div>
  );
}
