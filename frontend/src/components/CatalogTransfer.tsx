import { useRef, useState, type ReactNode } from "react";
import { Download, Upload } from "lucide-react";

interface CatalogEntityBundle {
  format: "okto-nexus.catalog";
  version: 2;
  catalog: string;
  exported_at: string;
  item: unknown;
}

export function uniqueImportedName(name: string, existing: Set<string>): string {
  const base = name.trim() || "Imported item";
  if (!existing.has(base.toLocaleLowerCase())) {
    existing.add(base.toLocaleLowerCase());
    return base;
  }
  let number = 2;
  while (existing.has(`${base} (imported ${number})`.toLocaleLowerCase())) number += 1;
  const result = `${base} (imported ${number})`;
  existing.add(result.toLocaleLowerCase());
  return result;
}

export function catalogEntityFilename(prefix: string, name: string): string {
  const slug = name
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLocaleLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 72);
  return `${prefix}-${slug || "item"}.json`;
}

function parseEntityBundle(value: unknown, catalog: string): unknown {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`This is not a valid ${catalog} export.`);
  }
  const parsed = value as Record<string, unknown>;
  if (parsed.format !== "okto-nexus.catalog" || parsed.catalog !== catalog) {
    throw new Error(`This is not a valid ${catalog} export.`);
  }
  if (parsed.version === 2 && "item" in parsed) return parsed.item;
  if (parsed.version === 1 && Array.isArray(parsed.items)) {
    if (parsed.items.length !== 1) {
      throw new Error(
        "Bulk catalog files are no longer supported. Import one entity at a time.",
      );
    }
    return parsed.items[0];
  }
  throw new Error(`This is not a valid ${catalog} entity export.`);
}

export function CatalogExportButton({
  catalog,
  filename,
  onExport,
  className = "btn btn-secondary",
  label = "Export JSON",
  title,
  testId,
}: {
  catalog: string;
  filename: string;
  onExport: () => Promise<unknown> | unknown;
  className?: string;
  label?: ReactNode | null;
  title?: string;
  testId?: string;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const exportJson = async () => {
    setBusy(true);
    setError(null);
    try {
      const bundle: CatalogEntityBundle = {
        format: "okto-nexus.catalog",
        version: 2,
        catalog,
        exported_at: new Date().toISOString(),
        item: await onExport(),
      };
      const blob = new Blob([JSON.stringify(bundle, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filename;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
    } catch (exc) {
      setError((exc as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <button
      className={className}
      disabled={busy}
      onClick={(event) => {
        event.stopPropagation();
        void exportJson();
      }}
      title={error ?? title ?? "Export this entity as JSON"}
      aria-label={title ?? "Export this entity as JSON"}
      data-testid={testId ?? `catalog-export-${catalog}`}
    >
      <Download size={13} /> {label}
    </button>
  );
}

export function CatalogImportButton({
  catalog,
  onImport,
}: {
  catalog: string;
  onImport: (item: unknown) => Promise<void>;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const importJson = async (file: File) => {
    setBusy(true);
    setError(null);
    setNote(null);
    try {
      const item = parseEntityBundle(JSON.parse(await file.text()), catalog);
      await onImport(item);
      setNote("Imported 1 entity.");
    } catch (exc) {
      setError((exc as Error).message);
    } finally {
      if (inputRef.current) inputRef.current.value = "";
      setBusy(false);
    }
  };

  return (
    <div
      className="flex items-center gap-1.5 flex-wrap"
      data-testid={`catalog-import-${catalog}`}
    >
      <button
        className="btn btn-secondary"
        disabled={busy}
        onClick={() => inputRef.current?.click()}
        title={`Import one ${catalog} entity from JSON`}
      >
        <Upload size={13} /> Import JSON
      </button>
      <input
        ref={inputRef}
        type="file"
        accept="application/json,.json"
        className="hidden"
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) void importJson(file);
        }}
      />
      {note && (
        <span className="text-[10px] text-emerald-600 dark:text-emerald-400">
          {note}
        </span>
      )}
      {error && (
        <span
          className="text-[10px] text-red-500 max-w-72 truncate"
          title={error}
        >
          {error}
        </span>
      )}
    </div>
  );
}
