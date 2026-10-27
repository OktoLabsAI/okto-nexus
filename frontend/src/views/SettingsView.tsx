import { SettingsDrafts, type SettingsDraft } from "../components/SettingsDrafts";
// Settings: appearance, hub info, RUNTIME parameters (except dedicated
// product panels such as Metrics),
// non-exclusively: precedence CLI > env > stored > default) and store
// maintenance. Field grammar mirrors the Pulse RuntimeSettingsPanel:
// label + tiny description + bounded input, with a native tooltip
// (title) on every field and amber "restart required" banner.

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Database,
  Eraser,
  MessagesSquare,
  Moon,
  RotateCcw,
  Save,
  SlidersHorizontal,
  Sun,
  ToggleLeft,
  Trash2,
} from "lucide-react";
import { api, type NexusInfo, type SettingItem } from "../api";
import { browserNotifyEnabled, setBrowserNotify } from "../operatorUnread";
import { useConfirm } from "../components/Confirm";
import { useTheme } from "../hooks/useTheme";
import { OperatorAccess } from "../components/OperatorAccess";
import { RuntimePolicy } from "../components/RuntimePolicy";

function labelOf(key: string): string {
  return key
    .replace(/_/g, " ")
    .replace(/\b(ttl|ms|md)\b/g, (m) => m.toUpperCase())
    .replace(/^./, (c) => c.toUpperCase());
}

function choiceLabel(item: SettingItem, choice: string): string {
  if (item.key === "remote_machine_policy") {
    return ({ manual: "Require approval (default)", deny: "Deny another machine", auto_replace: "Accept and revoke previous machine" } as Record<string, string>)[choice] ?? choice;
  }
  if (item.key === "transport_security") {
    return choice === "http_https"
      ? "HTTP + HTTPS / WS + WSS (default)"
      : "HTTPS / WSS only";
  }
  if (item.key === "meta_harness_receipt_display") {
    return choice === "inline"
      ? "Status flags (default)"
      : "Timeline receipt messages";
  }
  return choice;
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
                {choiceLabel(item, c)}
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

export function SettingsView({
  onSettingsApplied, onPendingChange,
}: {
  onSettingsApplied?: () => void | Promise<unknown>;
  onPendingChange?: (pending: boolean) => void;
}) {
  const { theme, toggle } = useTheme();
  const [themeDraft, setThemeDraft] = useState(theme);
  const [tab, setTab] = useState('Interface');
  const [sections, setSections] = useState<Record<string, SettingsDraft>>({});
  const register = useCallback((id: string, draft: SettingsDraft | null) => {
    setSections(current => {const next = {...current}; if (draft) next[id] = draft; else delete next[id]; return next;});
  }, []);
  const { confirm, dialog } = useConfirm();
  const [info, setInfo] = useState<NexusInfo | null>(null);
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
      .then(setInfo)
      .catch(() => undefined);
    loadSettings();
  }, []);

  const dirtyKeys = useMemo(
    () =>
      Object.keys(drafts).filter((key) => {
        const item = items.find((i) => i.key === key);
        return item && (item.type === "int" ? Number(drafts[key]) !== Number(item.value) : drafts[key] !== item.value);
      }),
    [drafts, items],
  );
  const generalItems = useMemo(
    () => items.filter((i) => i.group === "general" && !["trust_mode", "transport_security", "remote_machine_policy", "connection_key_ttl_seconds", "poll_token_ttl_seconds", "expose_workspace_path"].includes(i.key) && !i.key.startsWith("retention_") && i.key !== "auto_prune_on_start"),
    [items],
  );
  const interfaceItems = useMemo(
    () => items.filter((i) => i.group === "interface"),
    [items],
  );
  const featureItems = useMemo(
    () => items.filter((i) => i.group === "features"),
    [items],
  );
  const dirty = dirtyKeys.length > 0 || themeDraft !== theme || Object.values(sections).some(s => s.dirty);
  const invalid = items.some(item => dirtyKeys.includes(item.key) && item.type === 'int' &&
    (drafts[item.key] === '' || !Number.isInteger(Number(drafts[item.key])) || (item.min !== null && Number(drafts[item.key]) < item.min) || (item.max !== null && Number(drafts[item.key]) > item.max)));
  const blocked = invalid || Object.values(sections).some(s => s.dirty && !s.valid);
  useEffect(() => {onPendingChange?.(dirty || saving); return () => onPendingChange?.(false);}, [dirty, saving, onPendingChange]);
  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => {if (dirty || saving) {event.preventDefault(); event.returnValue = '';}};
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [dirty, saving]);
  const restartTouched = dirtyKeys.some(
    (key) => items.find((i) => i.key === key)?.requires_restart,
  );

  const save = async () => {
    if (blocked || saving) return;
    setSaving(true);
    setReport(null);
    try {
      const changes: Record<string, unknown> = {};
      for (const key of dirtyKeys) changes[key] = items.find(i => i.key === key)?.type === 'int' ? Number(drafts[key]) : drafts[key];
      // Each endpoint commits independently. Clear only successful sections so retry is safe.
      if (dirtyKeys.length) {
        await api.updateSettings(changes);
        setItems(current => current.map(item => Object.prototype.hasOwnProperty.call(changes, item.key) ? {...item, value: changes[item.key] as SettingItem['value']} : item));
        setDrafts({});
      }
      for (const [id, section] of Object.entries(sections).sort(([a], [b]) => Number(a === 'operator') - Number(b === 'operator'))) {
        if (section.dirty && !await section.save()) throw new Error(`Could not save ${id}. Review its tab. Successfully saved sections were retained.`);
      }
      if (themeDraft !== theme) toggle();
      await onSettingsApplied?.();
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
    <SettingsDrafts.Provider value={register}><div className="h-full min-h-0 flex flex-col">
      {dialog}
      <header className="shrink-0 border-b border-surface-200 dark:border-surface-800 px-6 pt-5">
        <h1 className="text-lg font-semibold">Settings</h1>
        <p className="mt-1 mb-4 text-xs text-surface-500">Configure this Nexus instance. Changes across tabs are saved together.</p>
        <div role="tablist" aria-label="Settings categories" className="flex gap-1 overflow-x-auto">
          {['Interface', 'Runtime', 'Coordination', 'Security', 'Storage'].map(name => <button key={name} id={`settings-tab-${name}`} role="tab" aria-selected={tab === name} aria-controls={`settings-panel-${name}`} tabIndex={tab === name ? 0 : -1}
            onKeyDown={event => {const names = ['Interface', 'Runtime', 'Coordination', 'Security', 'Storage']; const index = names.indexOf(name); const next = event.key === 'ArrowRight' ? names[(index+1)%names.length] : event.key === 'ArrowLeft' ? names[(index+names.length-1)%names.length] : event.key === 'Home' ? names[0] : event.key === 'End' ? names[names.length-1] : null; if (next) {event.preventDefault(); setTab(next); document.getElementById(`settings-tab-${next}`)?.focus();}}}
            onClick={() => setTab(name)} className={`px-4 py-3 text-sm whitespace-nowrap border-b-2 ${tab === name ? 'border-accent-500 text-accent-600 dark:text-accent-400' : 'border-transparent text-surface-500 hover:text-surface-900 dark:hover:text-white'}`}>{name}</button>)}
        </div>
      </header>
      <div className="flex-1 min-h-0 overflow-y-auto p-6">
      <fieldset disabled={saving} className="min-w-0 space-y-5">
        <div role="tabpanel" id="settings-panel-Security" aria-labelledby="settings-tab-Security" hidden={tab !== 'Security'}><OperatorAccess />
          <section className="panel p-5 mt-5 grid sm:grid-cols-2 gap-5">{items.filter(i => ['trust_mode', 'transport_security', 'remote_machine_policy', 'connection_key_ttl_seconds', 'poll_token_ttl_seconds', 'expose_workspace_path'].includes(i.key)).map(item => <SettingField key={item.key} item={item} draft={drafts[item.key]} onChange={value => setDrafts(d => ({...d, [item.key]: value}))}/>)}</section>
        </div>
        <div role="tabpanel" id="settings-panel-Interface" aria-labelledby="settings-tab-Interface" hidden={tab !== 'Interface'} className="space-y-5">
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
            <button className="btn btn-secondary" onClick={() => setThemeDraft(value => value === "dark" ? "light" : "dark")}>
              {themeDraft === "dark" ? <Sun size={14} /> : <Moon size={14} />}
              {themeDraft === "dark" ? "Switch to light" : "Switch to dark"}
            </button>
          </div>
        </section>

        <OperatorNotifications />

        {interfaceItems.length > 0 && (
          <section className="panel p-5 space-y-4" data-testid="interface-settings">
            <div>
              <h2 className="font-display font-semibold text-sm flex items-center gap-2">
                <MessagesSquare size={14} /> Interface behavior
              </h2>
              <p className="mt-1 text-[11px] text-surface-400 dark:text-surface-500">
                Presentation preferences shared by operators using this Nexus instance.
              </p>
            </div>
            <div className="grid grid-cols-1 gap-x-6 gap-y-4 sm:grid-cols-2">
              {interfaceItems.map((item) => (
                <SettingField
                  key={item.key}
                  item={item}
                  draft={drafts[item.key]}
                  onChange={(value) =>
                    setDrafts((current) => ({ ...current, [item.key]: value }))
                  }
                />
              ))}
            </div>
          </section>
        )}

        </div>
        <div role="tabpanel" id="settings-panel-Storage" aria-labelledby="settings-tab-Storage" hidden={tab !== "Storage"} className="space-y-5">
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

        </div>
        <div role="tabpanel" id="settings-panel-Runtime" aria-labelledby="settings-tab-Runtime" hidden={tab !== 'Runtime'} className="space-y-5">
        <div className="panel p-5 text-sm"><RuntimePolicy /></div>
        <section className="panel p-5 space-y-4" data-testid="runtime-settings">
          <div className="flex items-center justify-between">
            <h2 className="font-display font-semibold text-sm flex items-center gap-2">
              <SlidersHorizontal size={14} /> Runtime parameters
            </h2>
            <button className="btn btn-secondary !text-xs" onClick={() => setDrafts(current => ({...current, ...Object.fromEntries(generalItems.filter(i => i.editable).map(i => [i.key, i.default]))}))}><RotateCcw size={12}/> Use parameter defaults</button>
          </div>
          <p className="text-[11px] text-surface-400 dark:text-surface-500">
            The same operational parameters as the CLI, non-exclusively —
            precedence: CLI flag &gt; environment variable &gt; value saved here
            &gt; default. Metrics has a dedicated panel in the header menu.
            Values pinned by a flag appear as{" "}
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
            {generalItems.map((item) => (
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

        </div>
        <div role="tabpanel" id="settings-panel-Coordination" aria-labelledby="settings-tab-Coordination" hidden={tab !== "Coordination"}>
        {/* Features (meta-harness opt-ins) */}
        {featureItems.length > 0 && (
          <section className="panel p-5 space-y-4" data-testid="feature-settings">
            <div className="flex items-center justify-between">
              <h2 className="font-display font-semibold text-sm flex items-center gap-2">
                <ToggleLeft size={14} /> Features
              </h2>
              <span className="chip bg-surface-200 text-surface-600 dark:bg-surface-700 dark:text-surface-300">
                Feature controls
              </span>
            </div>
            <p className="text-[11px] text-surface-400 dark:text-surface-500">
              Coordination features run when switched
              on here (or pinned via{" "}
              <span className="font-mono">OKTO_NEXUS_FEATURE_*</span> /{" "}
              <span className="font-mono">--feature-*</span>). Experimental
              surfaces may hide dashboard views immediately; any field marked
              restart changes the MCP tool schema only after restarting the
              server. Agents can read the effective flags via{" "}
              <span className="font-mono">nexus_info</span>.
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-4">
              {featureItems.map((item) => (
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
        )}

        </div>
        <div hidden={tab !== 'Storage'} className="space-y-5">
        <section className="panel p-5"><h2 className="text-sm font-semibold mb-4">Retention</h2><div className="grid sm:grid-cols-2 gap-5">{items.filter(i => i.key.startsWith('retention_') || i.key === 'auto_prune_on_start').map(item => <SettingField key={item.key} item={item} draft={drafts[item.key]} onChange={value => setDrafts(d => ({...d, [item.key]: value}))}/>)}</div></section>
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
                  title="Stops running executions and permanently erases operational history."
                >
                  Reset database
                </div>
                <p className="text-xs text-surface-500 mt-1">
                  Erases ALL messages, deliveries, handoffs, sessions,
                  events and channels. Running executions will stop. Irreversible.
                </p>
                <label
                  className="flex items-center gap-2 mt-2 text-xs text-surface-600 dark:text-surface-400"
                  title="Keeps identities, keys, workspaces, connection settings and permissions. Agents reconnect automatically."
                >
                  <input
                    type="checkbox"
                    checked={keepAgents}
                    onChange={(e) => setKeepAgents(e.target.checked)}
                    className="accent-accent-500"
                  />
                  Preserve agents, API keys and connection settings (recommended)
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
                          <b>Agents, keys, workspaces and connection settings will be preserved. Running executions will stop and agents will reconnect automatically.</b>
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
                        let result = await api.reset(keepAgents);
                        while (result.pending) {
                          const phases: Record<string, string> = {
                            stopping_executions: "Stopping running executions…",
                            clearing_history: "Clearing history…",
                            reconnecting: "Reconnecting agents…",
                          };
                          setReport(phases[String(result.phase)] ?? "Reset in progress…");
                          await new Promise((resolve) => setTimeout(resolve, 1000));
                          result = await api.resetStatus();
                        }
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

        </section>
        </div>
      </fieldset></div>
      <footer className="shrink-0 border-t border-surface-200 dark:border-surface-800 bg-white dark:bg-surface-950 px-6 py-4 flex items-center justify-between gap-4">
        <div className="min-w-0 text-xs" aria-live="polite">{error ? <p role="alert" className="text-red-500">{error}</p> : report ? <p className="break-words">{report}</p> : <p className="text-surface-500">{dirty ? 'Unsaved changes' : 'All changes saved'}</p>}{blocked && <p className="text-amber-600">Review invalid or incomplete fields before saving.</p>}</div>
        <button className="btn btn-primary shrink-0" disabled={!dirty || blocked || saving} onClick={() => void save()} data-testid="save-settings"><Save size={14}/>{saving ? 'Saving…' : 'Save changes'}</button>
      </footer>
    </div></SettingsDrafts.Provider>
  );
}

// Browser notification for new operator messages (issue #78). The switch is a
// preference of this browser: it is stored in localStorage and takes effect at
// once, so it does not join the unsaved-settings drafts.
function OperatorNotifications() {
  const supported = typeof Notification !== "undefined";
  const [enabled, setEnabled] = useState(browserNotifyEnabled);
  const [note, setNote] = useState<string | null>(null);
  const toggle = async () => {
    const next = await setBrowserNotify(!enabled);
    setEnabled(next);
    setNote(
      !enabled && !next
        ? "The browser did not grant the notification permission."
        : null,
    );
  };
  return (
    <section className="panel p-5 space-y-3" data-testid="operator-notifications">
      <h2 className="font-display font-semibold text-sm">Operator notifications</h2>
      <div className="flex items-center justify-between gap-3 text-sm">
        <span
          className="text-surface-600 dark:text-surface-400"
          title="Shows a browser notification when a message for the operator arrives and this tab is in the background. The preference is saved in this browser."
        >
          Browser notification for new operator messages
        </span>
        <button
          className="btn btn-secondary"
          onClick={() => void toggle()}
          disabled={!supported}
          aria-pressed={enabled}
          data-testid="operator-notify-toggle"
        >
          {enabled ? "On" : "Off"}
        </button>
      </div>
      {!supported && (
        <p className="text-[11px] text-surface-400">This browser has no Notification support.</p>
      )}
      {note && <p role="status" className="text-[11px] text-amber-600">{note}</p>}
    </section>
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
