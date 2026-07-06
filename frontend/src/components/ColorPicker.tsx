// ColorPicker (spec 2d6920f4): pick an agent's display color — a curated
// palette, any custom #RGB/#RRGGBB, or "Auto" (reset to the deterministic
// auto-by-identity color). null = auto; a hex string = that color verbatim.
// Reused in the agent create and edit forms. A live preview shows the actual
// header gradient + contrast-aware text the graph card will render.

import { useState } from "react";
import { RotateCcw } from "lucide-react";
import {
  agentColor,
  autoColor,
  gradientFor,
  isHexColor,
  textColorFor,
} from "../graph/agentColor";

// A curated palette (Tailwind-500 family) for quick picks. The operator can
// still type any valid hex, or reset to auto.
const PALETTE = [
  "#ef4444",
  "#f97316",
  "#f59e0b",
  "#eab308",
  "#22c55e",
  "#10b981",
  "#14b8a6",
  "#06b6d4",
  "#0ea5e9",
  "#3b82f6",
  "#6366f1",
  "#8b5cf6",
  "#a855f7",
  "#ec4899",
  "#f43f5e",
  "#64748b",
];

export function ColorPicker({
  value,
  agentId,
  onChange,
  idPrefix = "color",
}: {
  value: string | null;
  agentId: string;
  onChange: (color: string | null) => void;
  idPrefix?: string;
}) {
  // Raw text of the hex field, held locally so partial typing (e.g. "#8b5")
  // doesn't propagate until it is a valid color. Seeded from the current value.
  const [draft, setDraft] = useState<string>(isHexColor(value) ? value : "");

  const seed = agentId.trim() || "agent";
  const auto = autoColor(seed);
  const isAuto = !isHexColor(value);
  const effective = agentColor(seed, value);

  const pick = (hex: string) => {
    setDraft(hex);
    onChange(hex);
  };

  const reset = () => {
    setDraft("");
    onChange(null);
  };

  const onHex = (raw: string) => {
    setDraft(raw);
    const trimmed = raw.trim();
    if (trimmed === "") {
      onChange(null);
    } else if (isHexColor(trimmed)) {
      onChange(trimmed);
    }
    // else: hold — invalid partial input never propagates a bad color.
  };

  const draftInvalid = draft.trim() !== "" && !isHexColor(draft);

  return (
    <div className="space-y-2" data-testid={`${idPrefix}-picker`}>
      <div className="flex flex-wrap items-center gap-1.5">
        {/* Auto swatch — resets to the deterministic identity color. */}
        <button
          type="button"
          onClick={reset}
          title="Auto (color derived from the agent id)"
          data-testid={`${idPrefix}-auto`}
          className={`h-6 w-6 rounded-md border flex items-center justify-center text-[9px] font-semibold ${
            isAuto
              ? "ring-2 ring-accent-500 ring-offset-1 ring-offset-white dark:ring-offset-surface-800 border-transparent"
              : "border-surface-300 dark:border-surface-600"
          }`}
          style={{ background: auto, color: textColorFor(auto) }}
        >
          A
        </button>
        {PALETTE.map((hex) => {
          const selected = !isAuto && effective.toLowerCase() === hex.toLowerCase();
          return (
            <button
              type="button"
              key={hex}
              onClick={() => pick(hex)}
              title={hex}
              data-testid={`${idPrefix}-swatch-${hex}`}
              className={`h-6 w-6 rounded-md border ${
                selected
                  ? "ring-2 ring-accent-500 ring-offset-1 ring-offset-white dark:ring-offset-surface-800 border-transparent"
                  : "border-surface-300 dark:border-surface-600"
              }`}
              style={{ background: hex }}
            />
          );
        })}
      </div>
      <div className="flex items-center gap-2">
        <input
          value={draft}
          onChange={(e) => onHex(e.target.value)}
          placeholder="#8b5cf6"
          spellCheck={false}
          data-testid={`${idPrefix}-hex`}
          className={`rounded-lg border bg-white dark:bg-surface-800 px-2 py-1 text-xs font-mono w-24 focus:outline-none focus:ring-2 focus:ring-accent-500/40 ${
            draftInvalid
              ? "border-red-400 dark:border-red-500"
              : "border-surface-200 dark:border-surface-700"
          }`}
        />
        {!isAuto && (
          <button
            type="button"
            onClick={reset}
            className="inline-flex items-center gap-1 text-[11px] text-surface-500 dark:text-surface-400 hover:text-surface-700 dark:hover:text-surface-200"
            data-testid={`${idPrefix}-reset`}
          >
            <RotateCcw size={12} /> Auto
          </button>
        )}
        {/* Live preview of the card header gradient + contrast text. */}
        <span
          className="ml-auto inline-flex items-center rounded-md px-2 py-1 text-[11px] font-medium max-w-[10rem] truncate"
          style={{
            backgroundImage: gradientFor(effective),
            color: textColorFor(effective),
          }}
          data-testid={`${idPrefix}-preview`}
        >
          {seed}
        </span>
      </div>
    </div>
  );
}
