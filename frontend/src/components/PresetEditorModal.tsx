// Preset editor modal - the Pulse PresetEditorModal grammar: name +
// description inputs, Enable all / Disable all bulk actions, the flags
// editor, and a footer that adapts (view-only built-in -> "Clone to
// customize"; custom/new -> Save).

import { useMemo, useState } from "react";
import { Copy, Save, X } from "lucide-react";
import {
  api,
  type PermissionFlags,
  type PresetRow,
} from "../api";
import {
  countEnabled,
  mergeFlags,
  PermissionFlagsEditor,
} from "./PermissionFlagsEditor";

export function PresetEditorModal({
  preset,
  registry,
  descriptions,
  initialFlags,
  onClose,
  onSaved,
}: {
  preset: PresetRow | null; // null = creating a new preset
  registry: PermissionFlags;
  descriptions: Record<string, string>;
  initialFlags?: PermissionFlags; // template for new (e.g. cloned source)
  onClose: () => void;
  onSaved: () => void;
}) {
  const isBuiltin = preset?.is_builtin ?? false;
  const [name, setName] = useState(preset?.name ?? "");
  const [description, setDescription] = useState(preset?.description ?? "");
  const [flags, setFlags] = useState<PermissionFlags>(() =>
    mergeFlags(registry, preset?.flags ?? initialFlags ?? registry),
  );
  const [cloning, setCloning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const counts = useMemo(() => countEnabled(flags), [flags]);
  const editable = !isBuiltin || cloning;

  const bulk = (value: boolean) => {
    const updated: PermissionFlags = JSON.parse(JSON.stringify(flags));
    for (const entries of Object.values(updated)) {
      for (const key of Object.keys(entries)) {
        if (typeof entries[key] === "boolean") entries[key] = value;
      }
    }
    setFlags(updated);
  };

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      if (preset && !isBuiltin) {
        await api.updatePreset(preset.preset_id, {
          name: name.trim(),
          description: description.trim() || undefined,
          flags,
        });
      } else {
        await api.createPreset({
          name: name.trim(),
          description: description.trim() || undefined,
          flags,
        });
      }
      onSaved();
      onClose();
    } catch (exc) {
      setError((exc as Error).message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm flex items-center justify-center"
      onClick={onClose}
    >
      <div
        className="relative w-[760px] max-w-[95vw] bg-white dark:bg-surface-900 rounded-xl shadow-2xl max-h-[88vh] flex flex-col overflow-hidden border border-surface-200/50 dark:border-surface-700/50"
        onClick={(e) => e.stopPropagation()}
        data-testid="preset-editor"
      >
        <div className="px-5 py-3 border-b border-surface-200/60 dark:border-surface-700/50 flex items-center justify-between shrink-0">
          <div className="flex items-center gap-2">
            <h2 className="font-display font-semibold text-sm text-surface-900 dark:text-surface-100">
              {preset
                ? cloning
                  ? `Clone: ${preset.name}`
                  : preset.name
                : "New preset"}
            </h2>
            {isBuiltin && !cloning && (
              <span className="chip bg-surface-200 text-surface-600 dark:bg-surface-700 dark:text-surface-300">
                built-in · read-only
              </span>
            )}
            <span className="chip bg-surface-100 text-surface-500 dark:bg-surface-800 dark:text-surface-400">
              {counts.enabled}/{counts.total} enabled
            </span>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 text-surface-400 hover:text-surface-600 dark:hover:text-surface-300 hover:bg-surface-100 dark:hover:bg-white/10 rounded-lg"
          >
            <X size={16} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-5 space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs font-medium text-surface-600 dark:text-surface-300">
                Name
              </label>
              <input
                value={name}
                disabled={!editable}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Restricted worker"
                className="mt-1 w-full text-sm px-3 py-1.5 rounded-lg border border-surface-300 dark:border-surface-600 bg-white dark:bg-surface-800 disabled:opacity-50"
                data-testid="preset-name"
              />
            </div>
            <div>
              <label className="text-xs font-medium text-surface-600 dark:text-surface-300">
                Description
              </label>
              <input
                value={description}
                disabled={!editable}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="What this preset is for"
                className="mt-1 w-full text-sm px-3 py-1.5 rounded-lg border border-surface-300 dark:border-surface-600 bg-white dark:bg-surface-800 disabled:opacity-50"
              />
            </div>
          </div>

          {editable && (
            <div className="flex gap-2">
              <button className="btn btn-secondary !py-1 !text-xs" onClick={() => bulk(true)}>
                Enable all
              </button>
              <button className="btn btn-secondary !py-1 !text-xs" onClick={() => bulk(false)}>
                Disable all
              </button>
            </div>
          )}

          <PermissionFlagsEditor
            flags={flags}
            registry={registry}
            descriptions={descriptions}
            readOnly={!editable}
            onChange={setFlags}
          />

          {error && <p className="text-xs text-red-500">{error}</p>}
        </div>

        <div className="px-5 py-3 border-t border-surface-200/60 dark:border-surface-700/50 flex justify-end gap-2 shrink-0">
          {isBuiltin && !cloning ? (
            <button
              className="btn btn-primary"
              onClick={() => {
                setCloning(true);
                setName(`${preset?.name} (copy)`);
              }}
              data-testid="preset-clone"
            >
              <Copy size={14} /> Clone to customize
            </button>
          ) : (
            <button
              className="btn btn-primary"
              disabled={!name.trim() || saving}
              onClick={save}
              data-testid="preset-save"
            >
              <Save size={14} /> {preset && !isBuiltin ? "Save preset" : "Create preset"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
