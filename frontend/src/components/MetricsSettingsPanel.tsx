import { useEffect, useState } from "react";
import { Gauge, Info, RotateCw, Save, X } from "lucide-react";
import {
  api,
  type MetricsMode,
  type MetricsPublishHealth,
  type MetricsSummary,
} from "../api";

interface MetricsSettingsPanelProps {
  initialPrompt?: boolean;
  onClose: () => void;
  onSaved?: () => void | Promise<unknown>;
}

const ACK_ITEMS = [
  {
    label: "Telemetry schema reviewed",
    description: "Only documented anonymous aggregate fields are eligible.",
  },
  {
    label: "Privacy terms reviewed",
    description: "Metrics sharing is optional and can be turned off here.",
  },
  {
    label: "Hourly aggregates only",
    description: "Events are summarized before upload.",
  },
  {
    label: "No PII or project content",
    description: "Messages, paths, titles and payload bodies are not sent.",
  },
] as const;

function displayDate(value?: string | null): string {
  if (!value) return "—";
  return value.replace("T", " ").replace(/\.\d+Z?$/, "Z");
}

function Stat({
  label,
  value,
}: {
  label: string;
  value: number | string | undefined;
}) {
  return (
    <div className="rounded-lg border border-surface-200 dark:border-surface-700 bg-surface-50 dark:bg-surface-900 px-3 py-2">
      <div className="text-sm font-semibold text-surface-800 dark:text-surface-100">
        {value ?? "—"}
      </div>
      <div className="text-[10px] uppercase tracking-wider text-surface-400">
        {label}
      </div>
    </div>
  );
}

function toUiMode(mode: unknown): MetricsMode {
  return mode === "anonymous_beacon" ? "anonymous_beacon" : "disabled";
}

function toServerMode(mode: unknown): MetricsMode {
  if (mode === "anonymous_beacon" || mode === "local_only") return mode;
  return "disabled";
}

function modeLabel(mode: MetricsMode): string {
  return mode === "anonymous_beacon" ? "On" : "Off";
}

export function MetricsSettingsPanel({
  initialPrompt = false,
  onClose,
  onSaved,
}: MetricsSettingsPanelProps) {
  const [modeEditable, setModeEditable] = useState(true);
  const [serverMode, setServerMode] = useState<MetricsMode>("disabled");
  const [draftMode, setDraftMode] = useState<MetricsMode>("disabled");
  const [summary, setSummary] = useState<MetricsSummary | null>(null);
  const [health, setHealth] = useState<MetricsPublishHealth | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [report, setReport] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const hasUnsavedChanges = draftMode !== serverMode;

  const refresh = async () => {
    setLoading(true);
    try {
      const [settingsPayload, nextSummary, nextHealth] = await Promise.all([
        api.settings(),
        api.metricsSummary(),
        api.metricsPublishHealth(),
      ]);
      const modeItem = settingsPayload.items.find((item) => item.key === "metrics_mode");
      const nextServerMode = toServerMode(modeItem?.value ?? nextSummary.mode);
      setModeEditable(modeItem?.editable ?? true);
      setServerMode(nextServerMode);
      setDraftMode(toUiMode(nextServerMode));
      setSummary(nextSummary);
      setHealth(nextHealth);
      setError(null);
    } catch (exc) {
      setError((exc as Error).message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
  }, []);

  const save = async () => {
    if (!hasUnsavedChanges) {
      if (initialPrompt) onClose();
      return;
    }
    setSaving(true);
    try {
      await api.updateSettings({ metrics_mode: draftMode });
      await refresh();
      await onSaved?.();
      setReport("Metrics settings saved.");
      if (initialPrompt) onClose();
    } catch (exc) {
      setError((exc as Error).message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-[1000] flex items-start justify-end bg-black/30 backdrop-blur-sm pt-14"
      onClick={onClose}
    >
      <div
        className="mr-4 max-h-[calc(100vh-4rem)] w-[560px] max-w-[calc(100vw-2rem)] overflow-y-auto rounded-xl border border-surface-200 bg-white p-4 shadow-2xl dark:border-surface-700 dark:bg-surface-900"
        onClick={(e) => e.stopPropagation()}
        data-testid="metrics-settings-panel"
      >
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            <h2 className="flex items-center gap-2 font-display text-sm font-semibold text-surface-900 dark:text-surface-100">
              <Gauge size={16} />
              {initialPrompt ? "Metrics opt-in" : "Metrics"}
            </h2>
            <p className="mt-1 text-xs text-surface-500 dark:text-surface-400">
              {summary
                ? `Current setting: ${modeLabel(serverMode)}${
                    hasUnsavedChanges ? ` · selected: ${modeLabel(draftMode)}` : ""
                  }`
                : "Loading metrics status"}
            </p>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-surface-400 transition-colors hover:bg-surface-100 hover:text-surface-700 dark:hover:bg-white/10 dark:hover:text-surface-200"
            aria-label="Close metrics settings"
          >
            <X size={16} />
          </button>
        </div>

        {loading ? (
          <p className="text-sm text-surface-500">Loading metrics…</p>
        ) : (
          <div className="space-y-5">
            {initialPrompt && (
              <div className="rounded-lg border border-sky-200 bg-sky-50 p-3 text-sm text-sky-950 dark:border-sky-900/70 dark:bg-sky-950/30 dark:text-sky-100">
                Okto Nexus starts with metrics disabled. Anonymous aggregate
                publishing is optional and can be changed later.
              </div>
            )}

            <div className="grid grid-cols-3 gap-2">
              <Stat label="events" value={summary?.event_count} />
              <Stat label="pending" value={summary?.pending_count} />
              <Stat label="sent" value={summary?.sent_count} />
            </div>

            <section className="space-y-2">
              <div className="flex items-center justify-between rounded-lg border border-surface-200 p-4 dark:border-surface-700">
                <div>
                  <div className="text-sm font-medium text-surface-900 dark:text-surface-100">
                    Send metrics
                  </div>
                  <div className="mt-1 text-xs text-surface-500 dark:text-surface-400">
                    {modeLabel(draftMode)}
                  </div>
                </div>
                <button
                  type="button"
                  role="switch"
                  aria-checked={draftMode === "anonymous_beacon"}
                  disabled={!modeEditable || saving}
                  data-testid="metrics-on-off-toggle"
                  onClick={() =>
                    setDraftMode((current) =>
                      current === "anonymous_beacon" ? "disabled" : "anonymous_beacon",
                    )
                  }
                  className={`relative h-7 w-12 rounded-full transition disabled:opacity-50 ${
                    draftMode === "anonymous_beacon"
                      ? "bg-accent-600"
                      : "bg-surface-300 dark:bg-surface-700"
                  }`}
                >
                  <span
                    className={`absolute top-1 h-5 w-5 rounded-full bg-white shadow transition ${
                      draftMode === "anonymous_beacon" ? "left-6" : "left-1"
                    }`}
                  />
                </button>
              </div>
              {!modeEditable && (
                <p className="text-xs text-amber-600 dark:text-amber-300">
                  Metrics mode is pinned by CLI or environment for this run.
                </p>
              )}
            </section>

            <div className="rounded-lg border border-surface-200 p-3 dark:border-surface-700" data-testid="metrics-scope">
              <div className="text-xs font-medium text-surface-900 dark:text-surface-100">
                Metrics scope
              </div>
              <div className="mt-1 text-xs leading-5 text-surface-500 dark:text-surface-400">
                All eligible anonymous aggregate metrics are included when sending is on.
              </div>
            </div>

            <section className="rounded-lg border border-surface-200 p-3 dark:border-surface-700">
              <h3 className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-surface-500">
                <Info size={13} />
                Anonymous metrics included
              </h3>
              <div className="space-y-2">
                {ACK_ITEMS.map((item) => (
                  <div
                    key={item.label}
                    className="flex gap-3 rounded-md border border-surface-200 p-3 text-left dark:border-surface-700"
                  >
                    <span className="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center text-accent-600 dark:text-accent-300">
                      <Info size={14} aria-hidden="true" />
                    </span>
                    <span className="min-w-0">
                      <span className="block text-xs font-medium text-surface-800 dark:text-surface-100">
                        {item.label}
                      </span>
                      <span className="mt-0.5 block text-xs leading-5 text-surface-500 dark:text-surface-400">
                        {item.description}
                      </span>
                    </span>
                  </div>
                ))}
              </div>
            </section>

            <section className="space-y-2 rounded-lg border border-surface-200 p-3 text-xs dark:border-surface-700">
              <div className="flex items-center justify-between">
                <span className="text-surface-500">Schema</span>
                <span className="font-mono text-surface-700 dark:text-surface-300">
                  {summary?.schema_version ?? "—"}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-surface-500">Publish health</span>
                <span className="text-surface-700 dark:text-surface-300">
                  {health?.status ?? "—"}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-surface-500">Last success</span>
                <span className="text-surface-700 dark:text-surface-300">
                  {displayDate(health?.last_success_at)}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-surface-500">Last failure</span>
                <span className="text-surface-700 dark:text-surface-300">
                  {displayDate(health?.last_failure_at)}
                </span>
              </div>
              {health?.reason_code && (
                <div className="flex items-center justify-between">
                  <span className="text-surface-500">Reason</span>
                  <span className="text-surface-700 dark:text-surface-300">
                    {health.reason_code}
                  </span>
                </div>
              )}
            </section>

            {summary?.storage_dir && (
              <div className="rounded-lg bg-surface-100 p-2 font-mono text-[11px] text-surface-500 dark:bg-surface-950 dark:text-surface-400">
                {summary.storage_dir}
              </div>
            )}

            {report && (
              <pre className="overflow-x-auto rounded-lg bg-surface-100 p-2 text-[11px] text-surface-600 dark:bg-surface-950 dark:text-surface-400">
                {report}
              </pre>
            )}
            {error && <p className="text-xs text-red-500">{error}</p>}

            <div className="flex flex-wrap items-center justify-end gap-2 border-t border-surface-200 pt-3 dark:border-surface-700">
              <button
                type="button"
                className="btn btn-secondary !text-xs"
                onClick={refresh}
                disabled={loading || saving}
              >
                <RotateCw size={14} />
                Refresh
              </button>
              <button
                type="button"
                className="btn btn-primary !text-xs"
                disabled={saving || !hasUnsavedChanges}
                onClick={save}
                data-testid="metrics-save"
              >
                <Save size={14} />
                {saving ? "Saving…" : "Save"}
              </button>
              {initialPrompt && (
                <button type="button" className="btn btn-secondary !text-xs" onClick={onClose}>
                  Not now
                </button>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
