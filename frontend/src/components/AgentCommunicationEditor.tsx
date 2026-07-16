// Agent communication binding editor (spec 6f961722): the per-agent, breakout
// panel that sets the 4th axis — HOW the agent should communicate — surfaced
// SELF-ONLY on its whoami. A communication binding is SINGLE-SOURCE (the
// deliberate divergence from attached policies' N-way AND): exactly one of
//   • None    — no style (the whoami stays byte-identical to the pre-feature one)
//   • Inline  — a style embedded on this agent alone
//   • Global  — a reference to a reusable, versioned preset (latest | pinned)
// Saved as ONE row via PUT /agents/{id}/communication (inline XOR global; neither
// clears it). Operator-only; catalog-driven for the global leg. UI text English.

import { useEffect, useMemo, useState } from "react";
import { Eye } from "lucide-react";
import {
  api,
  type AgentRow,
  type CommContent,
  type CommGlobalRef,
  type CommPresetRecord,
  type CommResolvedBlock,
} from "../api";
import {
  CommContentChips,
  CommContentEditor,
} from "./CommContentEditor";

type Mode = "none" | "inline" | "global";

const segBtn = (active: boolean) =>
  `px-3 py-1.5 text-xs rounded-lg border transition-colors ${
    active
      ? "border-accent-300 dark:border-accent-700 bg-accent-100 text-accent-700 dark:bg-accent-900/40 dark:text-accent-300 font-medium"
      : "border-surface-200 dark:border-surface-700 text-surface-600 dark:text-surface-300 hover:bg-surface-50 dark:hover:bg-surface-800/50"
  }`;

const selectCls =
  "text-xs font-mono rounded-md border border-surface-300 dark:border-surface-600 bg-white dark:bg-surface-800 px-1.5 py-1 text-surface-700 dark:text-surface-200 focus:outline-none focus:ring-2 focus:ring-accent-500/40";

export function AgentCommunicationEditor({
  agent,
  onSaved,
  onClose,
}: {
  agent: AgentRow;
  onSaved: () => Promise<void> | void;
  onClose: () => void;
}) {
  const [mode, setMode] = useState<Mode>("none");
  const [inline, setInline] = useState<CommContent>({});
  const [globalRef, setGlobalRef] = useState<CommGlobalRef | null>(null);
  const [catalog, setCatalog] = useState<CommPresetRecord[]>([]);
  // The selected global preset's full record (versions) — fetched on demand so
  // the version picker is bounded and the preview resolves the real content.
  const [selectedDetail, setSelectedDetail] = useState<CommPresetRecord | null>(
    null,
  );
  const [saved, setSaved] = useState<CommResolvedBlock | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  // Load the catalog + the agent's current binding (reshaped for this editor).
  useEffect(() => {
    api
      .commPresets()
      .then(({ items }) => setCatalog(items))
      .catch(() => undefined);
    api
      .agentCommunication(agent.agent_id)
      .then((binding) => {
        setSaved(binding.communication);
        if (binding.inline) {
          setMode("inline");
          setInline(binding.inline);
        } else if (binding.global) {
          setMode("global");
          setGlobalRef(binding.global);
        } else {
          setMode("none");
        }
      })
      .catch(() => undefined);
  }, [agent.agent_id]);

  // Fetch the selected global preset's versions whenever the reference changes.
  useEffect(() => {
    if (mode !== "global" || !globalRef?.preset_id) {
      setSelectedDetail(null);
      return;
    }
    let cancelled = false;
    api
      .commPreset(globalRef.preset_id)
      .then((rec) => {
        if (!cancelled) setSelectedDetail(rec);
      })
      .catch(() => {
        if (!cancelled) setSelectedDetail(null);
      });
    return () => {
      cancelled = true;
    };
  }, [mode, globalRef?.preset_id]);

  const presetById = useMemo(
    () => new Map(catalog.map((p) => [p.preset_id, p])),
    [catalog],
  );

  // Live preview of what the agent's whoami would show for the pending choice.
  const preview: CommResolvedBlock | null = useMemo(() => {
    if (mode === "inline") return { source: "inline", content: inline };
    if (mode === "global" && globalRef?.preset_id && selectedDetail) {
      const versions = selectedDetail.versions ?? [];
      const chosen =
        globalRef.mode === "pinned"
          ? versions.find((v) => v.version === globalRef.pinned_version)
          : versions.reduce<(typeof versions)[number] | undefined>(
              (max, v) => (!max || v.version > max.version ? v : max),
              undefined,
            );
      if (!chosen) return null;
      return {
        source: `${globalRef.preset_id}@${chosen.version}`,
        content: chosen.content,
      };
    }
    return null;
  }, [mode, inline, globalRef, selectedDetail]);

  const pickPreset = (presetId: string) => {
    if (!presetId) {
      setGlobalRef(null);
      return;
    }
    setGlobalRef({ preset_id: presetId, mode: "latest" });
  };

  const latestOf = (presetId: string | undefined) =>
    presetId ? (presetById.get(presetId)?.latest_version ?? 0) : 0;

  const setGlobalMode = (next: "latest" | "pinned") => {
    setGlobalRef((cur) => {
      if (!cur) return cur;
      if (next === "pinned") {
        const latest =
          selectedDetail?.latest_version ?? latestOf(cur.preset_id) ?? 1;
        return {
          preset_id: cur.preset_id,
          mode: "pinned",
          pinned_version: cur.pinned_version ?? latest ?? 1,
        };
      }
      return { preset_id: cur.preset_id, mode: "latest" };
    });
  };

  const save = async () => {
    setSaving(true);
    try {
      let body: { inline?: CommContent; global?: CommGlobalRef } = {};
      if (mode === "inline") body = { inline };
      else if (mode === "global" && globalRef?.preset_id) body = { global: globalRef };
      // mode === "none" (or a global with no preset chosen) -> {} clears it.
      const result = await api.setAgentCommunication(agent.agent_id, body);
      setSaved(result.communication);
      setError(null);
      await onSaved();
      onClose();
    } catch (exc) {
      setError((exc as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const latest = selectedDetail?.latest_version ?? latestOf(globalRef?.preset_id);
  const globalIncomplete = mode === "global" && !globalRef?.preset_id;

  return (
    <div
      className="space-y-4 rounded-xl border border-surface-200 dark:border-surface-700 p-3 animate-slide-up"
      data-testid={`communication-panel-${agent.agent_id}`}
    >
      <div>
        <h3 className="text-xs font-semibold tracking-wide text-surface-700 dark:text-surface-200 mb-1">
          Communication style
        </h3>
        <p className="text-xs text-surface-500 dark:text-surface-400">
          Tells this agent HOW to communicate — shown SELF-ONLY on its{" "}
          <code className="font-mono">whoami</code>, never on any discovery
          surface. Choose an inline style unique to this agent, or reference a
          reusable preset from the Communication catalog.
        </p>
      </div>

      {/* Source segmented control (single-source: None / Inline / Global) */}
      <div className="flex items-center gap-2" data-testid="comm-mode">
        <button
          className={segBtn(mode === "none")}
          onClick={() => setMode("none")}
          data-testid="comm-mode-none"
        >
          None
        </button>
        <button
          className={segBtn(mode === "inline")}
          onClick={() => setMode("inline")}
          data-testid="comm-mode-inline"
        >
          Inline
        </button>
        <button
          className={segBtn(mode === "global")}
          onClick={() => setMode("global")}
          data-testid="comm-mode-global"
        >
          Preset
        </button>
      </div>

      {mode === "none" && (
        <p className="text-xs text-surface-400 dark:text-surface-500">
          No communication style — this agent's whoami carries no style block.
        </p>
      )}

      {mode === "inline" && (
        <CommContentEditor
          value={inline}
          onChange={setInline}
          idPrefix={`inline-${agent.agent_id}`}
          testId={`inline-comm-${agent.agent_id}`}
        />
      )}

      {mode === "global" && (
        <div className="space-y-2">
          {catalog.length === 0 ? (
            <p className="text-xs text-surface-400 dark:text-surface-500">
              No communication presets exist yet — create them in the
              Communication screen.
            </p>
          ) : (
            <div className="flex flex-wrap items-center gap-2">
              <select
                value={globalRef?.preset_id ?? ""}
                onChange={(e) => pickPreset(e.target.value)}
                className={`${selectCls} min-w-[180px]`}
                data-testid="comm-global-preset"
              >
                <option value="">Select a preset…</option>
                {catalog.map((p) => (
                  <option key={p.preset_id} value={p.preset_id}>
                    {p.name}
                    {p.latest_version === 0
                      ? " (no versions)"
                      : ` (@v${p.latest_version})`}
                  </option>
                ))}
              </select>
              {globalRef?.preset_id && (
                <>
                  <select
                    value={globalRef.mode}
                    onChange={(e) =>
                      setGlobalMode(e.target.value as "latest" | "pinned")
                    }
                    className={selectCls}
                    title="latest follows the newest version; pinned freezes on one"
                    data-testid="comm-global-mode"
                  >
                    <option value="latest">latest</option>
                    <option value="pinned" disabled={latest === 0}>
                      pinned
                    </option>
                  </select>
                  {globalRef.mode === "pinned" && (
                    <select
                      value={globalRef.pinned_version ?? latest}
                      onChange={(e) =>
                        setGlobalRef((cur) =>
                          cur
                            ? { ...cur, pinned_version: Number(e.target.value) }
                            : cur,
                        )
                      }
                      className={selectCls}
                      data-testid="comm-global-version"
                    >
                      {Array.from({ length: latest }, (_, i) => latest - i).map(
                        (v) => (
                          <option key={v} value={v}>
                            @v{v}
                          </option>
                        ),
                      )}
                    </select>
                  )}
                </>
              )}
            </div>
          )}
        </div>
      )}

      {/* Live preview of the resolved whoami block */}
      {mode !== "none" && (
        <div className="flex items-start gap-2 rounded-lg border border-accent-200 dark:border-accent-800/50 bg-accent-50/50 dark:bg-accent-900/10 px-3 py-2.5">
          <Eye size={14} className="text-accent-500 dark:text-accent-400 mt-0.5 shrink-0" />
          <div className="min-w-0">
            <p className="text-xs text-surface-600 dark:text-surface-300 mb-1.5">
              whoami communication{" "}
              {preview ? (
                <span className="font-mono text-surface-500 dark:text-surface-400">
                  · source {preview.source}
                </span>
              ) : (
                <span className="text-surface-400 dark:text-surface-500">
                  · nothing resolves yet
                </span>
              )}
            </p>
            {preview && <CommContentChips content={preview.content} />}
          </div>
        </div>
      )}

      {error && <p className="text-xs text-red-500">{error}</p>}
      <div className="flex items-center gap-2">
        <button
          className="btn btn-primary"
          onClick={save}
          disabled={saving || globalIncomplete}
          title={
            globalIncomplete ? "Select a preset or switch source" : undefined
          }
          data-testid={`save-communication-${agent.agent_id}`}
        >
          Save changes
        </button>
        <button className="btn btn-secondary" onClick={onClose}>
          Cancel
        </button>
        {saved && (
          <span className="text-[10px] text-surface-400 dark:text-surface-500">
            Currently bound · source{" "}
            <span className="font-mono">{saved.source}</span>
          </span>
        )}
      </div>
    </div>
  );
}
