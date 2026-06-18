// TypeSelect — a typeahead combobox for picking an event type from the known
// set (derived from GET /events/types). Same grammar as AgentSelect; "(any)"
// or the inline ✕ clears it.

import { useEffect, useRef, useState } from "react";
import { ChevronDown, Search, X } from "lucide-react";

export function TypeSelect({
  value,
  onChange,
  types,
  label,
  placeholder = "any type",
}: {
  value: string;
  onChange: (type: string) => void;
  types: string[];
  label?: string;
  placeholder?: string;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  const q = query.trim().toLowerCase();
  const filtered = q ? types.filter((t) => t.toLowerCase().includes(q)) : types;

  const pick = (t: string) => {
    onChange(t);
    setQuery("");
    setOpen(false);
  };

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        data-testid="type-select"
        className="flex items-center gap-1.5 rounded-lg border border-surface-200 dark:border-surface-700 bg-white dark:bg-surface-800 px-2 py-1.5 text-xs min-w-[170px] focus:outline-none focus:ring-2 focus:ring-accent-500/40"
      >
        {label && <span className="text-surface-400 shrink-0">{label}:</span>}
        <span
          className={`font-mono truncate ${
            value ? "text-surface-800 dark:text-surface-200" : "text-surface-400"
          }`}
        >
          {value || placeholder}
        </span>
        {value ? (
          <X
            size={12}
            className="ml-auto shrink-0 text-surface-400 hover:text-surface-700 dark:hover:text-surface-200"
            onClick={(e) => {
              e.stopPropagation();
              pick("");
            }}
          />
        ) : (
          <ChevronDown size={12} className="ml-auto shrink-0 text-surface-400" />
        )}
      </button>

      {open && (
        <div className="absolute z-30 mt-1 w-64 max-h-72 overflow-hidden flex flex-col rounded-lg border border-surface-200 dark:border-surface-700 bg-white dark:bg-surface-800 shadow-xl">
          <div className="relative p-1.5 border-b border-surface-100 dark:border-surface-700">
            <Search
              size={12}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-surface-400"
            />
            <input
              autoFocus
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={`search ${types.length} types…`}
              className="w-full pl-6 pr-2 py-1 rounded text-xs bg-transparent focus:outline-none"
            />
          </div>
          <div className="overflow-y-auto">
            <button
              onClick={() => pick("")}
              className="w-full text-left px-3 py-1.5 text-xs text-surface-400 hover:bg-surface-50 dark:hover:bg-surface-700"
            >
              (any)
            </button>
            {filtered.map((t) => (
              <button
                key={t}
                onClick={() => pick(t)}
                className={`w-full text-left px-3 py-1.5 text-xs font-mono truncate hover:bg-surface-50 dark:hover:bg-surface-700 ${
                  t === value
                    ? "bg-accent-50 dark:bg-accent-900/30 text-surface-800 dark:text-surface-200"
                    : "text-surface-700 dark:text-surface-300"
                }`}
              >
                {t}
              </button>
            ))}
            {filtered.length === 0 && (
              <div className="px-3 py-2 text-xs text-surface-400">no match</div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
