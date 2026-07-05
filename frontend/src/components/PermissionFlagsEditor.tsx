// Permission flags editor - the Pulse PermissionFlagsEditor grammar adapted
// to the Nexus 2-level registry: group cards with toggle switches (green
// on / gray off), per-group enabled counters, numeric limits as inline
// inputs, plus a readOnly mode for built-ins. Data-driven from the server's
// registry, so retired flags (e.g. allowed_peers, removed in F1) never
// render.

import { useMemo } from "react";
import type { PermissionFlags } from "../api";

const GROUP_LABELS: Record<string, string> = {
  messages: "Messaging",
  handoffs: "Handoffs",
  channels: "Channels",
  artifacts: "Artifacts",
  events: "Observability",
  limits: "Limits",
};

const GROUP_COLORS: Record<string, string> = {
  messages: "text-sky-600 dark:text-sky-400",
  handoffs: "text-fuchsia-600 dark:text-fuchsia-400",
  channels: "text-emerald-600 dark:text-emerald-400",
  artifacts: "text-amber-600 dark:text-amber-400",
  events: "text-violet-600 dark:text-violet-400",
  limits: "text-surface-500 dark:text-surface-400",
};

export function mergeFlags(
  registry: PermissionFlags,
  flags: PermissionFlags | null | undefined,
): PermissionFlags {
  const merged: PermissionFlags = {};
  for (const [group, entries] of Object.entries(registry)) {
    merged[group] = {};
    for (const [flag, def] of Object.entries(entries)) {
      const stored = flags?.[group]?.[flag];
      merged[group][flag] = stored === undefined ? def : stored;
    }
  }
  return merged;
}

export function countEnabled(flags: PermissionFlags): {
  enabled: number;
  total: number;
} {
  let enabled = 0;
  let total = 0;
  for (const entries of Object.values(flags)) {
    for (const value of Object.values(entries)) {
      if (typeof value === "boolean") {
        total += 1;
        if (value) enabled += 1;
      }
    }
  }
  return { enabled, total };
}

function Toggle({
  enabled,
  readOnly,
  onToggle,
}: {
  enabled: boolean;
  readOnly: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      type="button"
      onClick={() => !readOnly && onToggle()}
      disabled={readOnly}
      className={`relative w-8 h-4 rounded-full transition-colors shrink-0 ${
        enabled ? "bg-emerald-500" : "bg-surface-300 dark:bg-surface-600"
      } ${readOnly ? "opacity-50 cursor-default" : "cursor-pointer"}`}
    >
      <span
        className={`absolute top-0.5 w-3 h-3 rounded-full bg-white transition-transform ${
          enabled ? "right-0.5" : "left-0.5"
        }`}
      />
    </button>
  );
}

export function PermissionFlagsEditor({
  flags,
  registry,
  descriptions,
  onChange,
  readOnly = false,
}: {
  flags: PermissionFlags;
  registry: PermissionFlags;
  descriptions: Record<string, string>;
  onChange?: (flags: PermissionFlags) => void;
  readOnly?: boolean;
}) {
  const merged = useMemo(() => mergeFlags(registry, flags), [registry, flags]);

  const set = (group: string, flag: string, value: boolean | number) => {
    if (readOnly || !onChange) return;
    const updated: PermissionFlags = JSON.parse(JSON.stringify(merged));
    updated[group][flag] = value;
    onChange(updated);
  };

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
      {Object.entries(merged).map(([group, entries]) => {
        const bools = Object.entries(entries).filter(
          ([, v]) => typeof v === "boolean",
        );
        const on = bools.filter(([, v]) => v === true).length;
        return (
          <div
            key={group}
            className="rounded-lg border border-surface-200 dark:border-surface-700 bg-surface-50/60 dark:bg-surface-900/60 p-3"
            data-testid={`perm-group-${group}`}
          >
            <div className="flex items-center justify-between mb-2">
              <span
                className={`text-xs font-semibold uppercase tracking-wide ${
                  GROUP_COLORS[group] ?? "text-surface-500"
                }`}
              >
                {GROUP_LABELS[group] ?? group}
              </span>
              {bools.length > 0 && (
                <span
                  className={`chip text-[10px] ${
                    on === bools.length
                      ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300"
                      : on === 0
                        ? "bg-red-100 text-red-600 dark:bg-red-900/40 dark:text-red-300"
                        : "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300"
                  }`}
                >
                  {on}/{bools.length}
                </span>
              )}
            </div>
            <div className="space-y-2">
              {Object.entries(entries).map(([flag, value]) => {
                const tip = descriptions[`${group}.${flag}`] ?? "";
                if (typeof value === "boolean") {
                  return (
                    <div
                      key={flag}
                      className="flex items-center justify-between gap-2"
                      title={tip}
                    >
                      <span className="text-xs text-surface-700 dark:text-surface-300 font-mono">
                        {flag}
                      </span>
                      <Toggle
                        enabled={value}
                        readOnly={readOnly}
                        onToggle={() => set(group, flag, !value)}
                      />
                    </div>
                  );
                }
                // number (the quantitative limits)
                return (
                  <div
                    key={flag}
                    className="flex items-center justify-between gap-2"
                    title={tip}
                  >
                    <span className="text-xs text-surface-700 dark:text-surface-300 font-mono">
                      {flag}
                    </span>
                    <div className="flex items-center gap-1">
                      <input
                        type="number"
                        min={0}
                        value={value}
                        disabled={readOnly}
                        onChange={(e) =>
                          set(group, flag, Math.max(0, Number(e.target.value) || 0))
                        }
                        className="w-20 text-xs px-2 py-0.5 rounded border border-surface-300 dark:border-surface-600 bg-white dark:bg-surface-800 disabled:opacity-50"
                      />
                      <span className="text-[10px] text-surface-400">
                        0 = ∞
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}
