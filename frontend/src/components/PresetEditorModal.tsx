import { AgentActionModal, AgentModalFooter } from './AgentActionModal';
// Preset editor modal - the Pulse PresetEditorModal grammar: name +
// description inputs, Enable all / Disable all bulk actions, the flags
// editor, and a footer that adapts (view-only built-in -> "Clone to
// customize"; custom/new -> Save).

import { useMemo, useState } from "react";
import { Copy, Save } from "lucide-react";
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
<AgentActionModal title={preset ? (cloning ? `Clone: ${preset.name}` : preset.name) : "New permission preset"} onClose={onClose} wide testId="preset-editor" busy={saving}
  dirty={cloning || name !== (preset?.name ?? '') || description !== (preset?.description ?? '') || JSON.stringify(flags) !== JSON.stringify(mergeFlags(registry, preset?.flags ?? initialFlags ?? registry))}>
        <p className="text-xs text-surface-500">{isBuiltin && !cloning ? 'Built-in · read-only · ' : ''}{counts.enabled}/{counts.total} enabled</p>
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

        <AgentModalFooter>
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
        </AgentModalFooter>
    </AgentActionModal>
  );
}
