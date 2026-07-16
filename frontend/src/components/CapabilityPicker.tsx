// Catalog-driven capability picker (migration 014 / sm_44572557): chips of
// selected capability names + a "+ capability" dropdown listing ONLY names
// registered in the central capability catalog — no free-form input, so the
// fail-closed existence gate on POST/PATCH can only trip on registry races.
// Used by the AgentsView create form and identity editor in place of the
// old comma-separated text input.

import { X } from "lucide-react";
import type { CapabilityRow } from "../api";
import { Picker } from "./AgentTagsEditor";

const CHIP =
  "inline-flex items-center gap-1 text-xs px-2 py-1 rounded-md bg-accent-100 text-accent-700 dark:bg-accent-900/40 dark:text-accent-300 border border-accent-200 dark:border-accent-800/50 font-mono";

export function CapabilityPicker({
  selected,
  catalog,
  onChange,
}: {
  selected: string[];
  catalog: CapabilityRow[];
  onChange: (next: string[]) => void;
}) {
  const items = catalog.map((entry) => ({
    id: entry.name,
    label: (
      <span className="flex justify-between gap-2">
        <span className="font-mono">{entry.name}</span>
        {selected.includes(entry.name) ? (
          <span className="text-surface-400 dark:text-surface-500">added</span>
        ) : (
          entry.description && (
            <span
              className="text-surface-400 dark:text-surface-500 truncate max-w-32"
              title={entry.description}
            >
              {entry.description}
            </span>
          )
        )}
      </span>
    ),
    disabled: selected.includes(entry.name),
  }));
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {selected.map((name) => (
        <span key={name} className={CHIP}>
          {name}
          <button
            className="opacity-70 hover:opacity-100"
            onClick={() => onChange(selected.filter((n) => n !== name))}
            title={`Remove ${name}`}
          >
            <X size={11} />
          </button>
        </span>
      ))}
      <Picker
        trigger="+ capability"
        header="Registered capabilities"
        items={items}
        footer="Missing a name? Register it in Registry → Capabilities."
        filterable
        onPick={(name) => onChange([...selected, name])}
      />
    </div>
  );
}
