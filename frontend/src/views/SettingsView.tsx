// Settings: appearance, hub info, RUNTIME parameters (every CLI knob,
// non-exclusively: precedence CLI > env > stored > default) and store
// maintenance. Field grammar mirrors the Pulse RuntimeSettingsPanel:
// label + tiny description + bounded input, with a native tooltip
// (title) on every field and amber "restart required" banner.

import { useEffect, useMemo, useState } from "react";
import {
  Database,
  Eraser,
  Moon,
  RotateCcw,
  Save,
  SlidersHorizontal,
  Sun,
  Trash2,
} from "lucide-react";
import { api, type SettingItem } from "../api";
import { useConfirm } from "../components/Confirm";
import { useTheme } from "../hooks/useTheme";

function labelOf(key: string): string {
  return key
    .replace(/_/g, " ")
    .replace(/\b(ttl|ms|md)\b/g, (m) => m.toUpperCase())
    .replace(/^./, (c) => c.toUpperCase());
}

function SettingField({
  item,
  draft,
  onChange,
}: {
  item: SettingItem;
  draft: unknown;
  onChange: (value: unknown) => void;
}) {
  const value = draft ?? item.value;
  const outOfRange =
    item.type === "int" &&
    (!Number.isFinite(Number(value)) ||
      (item.min !== null && Number(value) < item.min) ||
      (item.max !== null && Number(value) > item.max));
  const dirty = draft !== undefined && draft !== item.value;

  return (
    <div title={item.description} data-testid={`setting-${item.key}`}>
      <label className="text-xs font-medium text-surface-700 dark:text-surface-200 mb-0.5 flex items-center gap-2">
        {labelOf(item.key)}
        {!item.editable && (
          <span className="chip bg-surface-200 text-surface-600 dark:bg-surface-700 dark:text-surface-300">
            cli/env
          </span>
        )}
        {item.requires_restart && (
          <span className="chip bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300">
            restart
          </span>
        )}
        {dirty && (
          <span className="w-1.5 h-1.5 rounded-full bg-accent-500" title="modified" />
        )}
      </label>
      <p className="text-[10px] text-surface-400 dark:text-surface-500 mb-1.5">
        {item.description}
      </p>
      <div className="flex items-center gap-2">
        {item.type === "bool" ? (
          <input
            type="checkbox"
            checked={Boolean(value)}
            disabled={!item.editable}
            onChange={(e) => onChange(e.target.checked)}
            className="accent-accent-500"
          />
        ) : item.type === "enum" ? (
          <select
            value={String(value)}
            disabled={!item.editable}
            onChange={(e) => onChange(e.target.value)}
            className="text-xs px-2 py-1 rounded-lg border border-surface-300 dark:border-surface-600 bg-white dark:bg-surface-800 disabled:opacity-50"
          >
            {(item.choices ?? []).map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        ) : (
          <>
            <input
              type="number"
              min={item.min ?? undefined}
              max={item.max ?? undefined}
              value={Number(value)}
              disabled={!item.editable}
              onChange={(e) => onChange(e.target.value)}
              className={`w-28 text-xs px-2 py-1 rounded-lg border bg-white dark:bg-surface-800 disabled:opacity-50 ${
                outOfRange
                  ? "border-red-400"
                  : "border-surface-300 dark:border-surface-600"
              }`}
            />
            <span className="text-[10px] text-surface-400">
              {item.min}–{item.max}
            </span>
          </>
        )}
      </div>
    </div>
  );
}

export function SettingsView() {
  const { theme, toggle } = useTheme();
  const { confirm, dialog } = useConfirm();
  const [info, setInfo] = useState<Record<string, unknown> | null>(null);
  const [items, setItems] = useState<SettingItem[]>([]);
  const [drafts, setDrafts] = useState<Record<string, unknown>>({});
  const [saving, setSaving] = useState(false);
  const [keepAgents, setKeepAgents] = useState(true);
  const [report, setReport] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadSettings = () =>
    api
      .settings()
      .then(({ items }) => {
        setItems(items);
        setDrafts({});
      })
      .catch((exc) => setError((exc as Error).message));

  useEffect(() => {
    api
      .info()
      .then((data) => setInfo(data as Record<string, unknown>))
      .catch(() => undefined);
    loadSettings();
  }, []);

  const dirtyKeys = useMemo(
    () =>
      Object.keys(drafts).filter((key) => {
        const item = items.find((i) => i.key === key);
        return item && drafts[key] !== item.value;
      }),
    [drafts, items],
  );
  const restartTouched = dirtyKeys.some(
    (key) => items.find((i) => i.key === key)?.requires_restart,
  );

  const save = async () => {
    setSaving(true);
    try {
      const changes: Record<string, unknown> = {};
      for (const key of dirtyKeys) changes[key] = drafts[key];
      await api.updateSettings(changes);
      await loadSettings();
      setReport("Settings saved and applied.");
      setError(null);
    } catch (exc) {
      setError((exc as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const runPrune = async (dryRun: boolean) => {
    try {
      const result = await api.prune(dryRun);
      setReport(
        (dryRun ? "Prune (dry run): " : "Prune executed: ") +
          JSON.stringify(result),
      );
      setError(null);
    } catch (exc) {
      setError((exc as Error).message);
    }
  };

  return (
    <div className="h-full overflow-y-auto p-6">
      {dialog}
      <div className="max-w-2xl mx-auto space-y-4">
        {/* Appearance */}
        <section className="panel p-5 space-y-3">
          <h2 className="font-display font-semibold text-sm">Appearance</h2>
          <div className="flex items-center justify-between text-sm">
            <span
              className="text-surface-600 dark:text-surface-400"
              title="Switches between light and dark themes; the preference is saved in this browser."
            >
              Interface theme
            </span>
            <button className="btn btn-secondary" onClick={toggle}>
              {theme === "dark" ? <Sun size={14} /> : <Moon size={14} />}
              {theme === "dark" ? "Switch to light" : "Switch to dark"}
            </button>
          </div>
        </section>

        {/* Hub info */}
        <section className="panel p-5 space-y-3">
          <h2 className="font-display font-semibold text-sm flex items-center gap-2">
            <Database size={14} /> Hub
          </h2>
          {info ? (
            <div className="grid grid-cols-3 gap-2 text-xs">
              <Info
                label="version"
                value={String(info.package_version ?? "—")}
                tip="Installed okto-nexus package version."
              />
              <Info
                label="schema"
                value={`v${info.schema_version ?? "—"}`}
                tip="Database schema version (applied migrations)."
              />
              <Info
                label="trust mode"
                value={String(info.trust_mode ?? "—")}
                tip="Trust mode in effect for sensitive MCP verbs."
              />
            </div>
          ) : (
            <p className="text-xs text-surface-500">loading…</p>
          )}
        </section>

        {/* Runtime parameters */}
        <section className="panel p-5 space-y-4" data-testid="runtime-settings">
          <div className="flex items-center justify-between">
            <h2 className="font-display font-semibold text-sm flex items-center gap-2">
              <SlidersHorizontal size={14} /> Runtime parameters
            </h2>
            <div className="flex gap-2">
              <button
                className="btn btn-secondary !py-1 !text-xs"
                title="Removes every stored override and restores defaults (values pinned by CLI/env are not affected)."
                onClick={() =>
                  confirm({
                    title: "Restore defaults?",
                    body: "Every stored override will be removed and the default values restored immediately.",
                    onConfirm: async () => {
                      await api.resetSettings();
                      await loadSettings();
                      setReport("Defaults restored.");
                    },
                  })
                }
              >
                <RotateCcw size={12} /> Defaults
              </button>
              <button
                className="btn btn-primary !py-1 !text-xs"
                disabled={dirtyKeys.length === 0 || saving}
                onClick={save}
                data-testid="save-settings"
              >
                <Save size={12} /> Save{dirtyKeys.length > 0 ? ` (${dirtyKeys.length})` : ""}
              </button>
            </div>
          </div>
          <p className="text-[11px] text-surface-400 dark:text-surface-500">
            The same parameters as the CLI, non-exclusively — precedence:
            CLI flag &gt; environment variable &gt; value saved here &gt;
            default. Values pinned by a flag appear as{" "}
            <span className="chip bg-surface-200 text-surface-600 dark:bg-surface-700 dark:text-surface-300">
              cli/env
            </span>{" "}
            and are read-only for this run.
          </p>
          {restartTouched && (
            <div className="text-[11px] px-3 py-2 rounded-lg bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800/50 text-amber-700 dark:text-amber-300">
              <b>Restart required.</b> Some changed values persist now but only
              take effect after restarting the serve.
            </div>
          )}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-4">
            {items.map((item) => (
              <SettingField
                key={item.key}
                item={item}
                draft={drafts[item.key]}
                onChange={(value) =>
                  setDrafts((d) => ({ ...d, [item.key]: value }))
                }
              />
            ))}
          </div>
        </section>

        {/* Maintenance */}
        <section className="panel p-5 space-y-4">
          <h2 className="font-display font-semibold text-sm flex items-center gap-2">
            <Eraser size={14} /> Store maintenance
          </h2>

          <div className="flex items-center justify-between text-sm">
            <div>
              <div
                className="text-surface-700 dark:text-surface-300"
                title="Applies the retention windows configured above: old events, read deliveries and closed sessions."
              >
                Prune (retention)
              </div>
              <p className="text-xs text-surface-500 dark:text-surface-500">
                Removes old events, read deliveries and closed sessions
                according to the retention windows.
              </p>
            </div>
            <div className="flex gap-2 shrink-0">
              <button
                className="btn btn-secondary"
                title="Counts what would be removed without deleting anything."
                onClick={() => runPrune(true)}
              >
                Simular
              </button>
              <button
                className="btn btn-secondary"
                title="Performs the removal according to the retention windows."
                onClick={() => runPrune(false)}
              >
                Executar
              </button>
            </div>
          </div>

          <div className="border-t border-surface-200/60 dark:border-surface-700/50 pt-4">
            <div className="flex items-start justify-between gap-4 text-sm">
              <div>
                <div
                  className="text-red-600 dark:text-red-400 font-medium"
                  title="Erases the hub's entire operational history (messages, handoffs, sessions, events, workspaces) with VACUUM. Irreversible."
                >
                  Reset database
                </div>
                <p className="text-xs text-surface-500 mt-1">
                  Erases ALL messages, deliveries, handoffs, sessions,
                  events, channels and workspaces (with VACUUM). Irreversible.
                </p>
                <label
                  className="flex items-center gap-2 mt-2 text-xs text-surface-600 dark:text-surface-400"
                  title="Keeps agent identities and API keys: the dashboard and connected MCP clients keep working after the reset."
                >
                  <input
                    type="checkbox"
                    checked={keepAgents}
                    onChange={(e) => setKeepAgents(e.target.checked)}
                    className="accent-accent-500"
                  />
                  Preserve agents and API keys (recommended)
                </label>
              </div>
              <button
                className="btn btn-danger shrink-0"
                data-testid="reset-db"
                onClick={() =>
                  confirm({
                    title: "Reset the database?",
                    body: (
                      <span>
                        The entire operational history will be permanently
                        erased.{" "}
                        {keepAgents ? (
                          <b>Agents and keys will be preserved.</b>
                        ) : (
                          <b className="text-red-500">
                            Agents and keys will ALSO be erased — every MCP
                            client loses access.
                          </b>
                        )}
                      </span>
                    ),
                    onConfirm: async () => {
                      try {
                        const result = await api.reset(keepAgents);
                        setReport("Database reset: " + JSON.stringify(result));
                        setError(null);
                      } catch (exc) {
                        setError((exc as Error).message);
                      }
                    },
                  })
                }
              >
                <Trash2 size={14} /> Reset…
              </button>
            </div>
          </div>

          {report && (
            <pre className="text-[11px] bg-surface-100 dark:bg-surface-900 rounded-lg p-2 overflow-x-auto text-surface-600 dark:text-surface-400">
              {report}
            </pre>
          )}
          {error && <p className="text-xs text-red-500">{error}</p>}
        </section>
      </div>
    </div>
  );
}

function Info({
  label,
  value,
  tip,
}: {
  label: string;
  value: string;
  tip: string;
}) {
  return (
    <div
      className="bg-surface-100 dark:bg-surface-900 rounded-lg p-2 text-center"
      title={tip}
    >
      <div className="font-mono text-surface-700 dark:text-surface-300">{value}</div>
      <div className="text-[10px] text-surface-500">{label}</div>
    </div>
  );
}
