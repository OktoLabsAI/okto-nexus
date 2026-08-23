// Communication presets (spec 6f961722, migration 023): the operator CATALOG of
// NAMED, versioned communication STYLES — the reusable half of the 4th per-agent
// axis (the inline half lives in the agent editor). A style tells an agent HOW to
// communicate and is surfaced SELF-ONLY on its whoami once bound. This is a
// full-bleed master-detail (a la PoliciesView): the catalog list on the left, the
// selected preset's header + append-only version history + a "publish new
// version" composer (the structured content editor) in the right inspector. Pure
// staging — a preset attaches to no one until an agent binds it; DELETE is refused
// (COMM_PRESET_IN_USE) while any agent still references it. UI text in English.

import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, MessageSquare, Plus, X } from "lucide-react";
import {
  api,
  ApiError,
  type CommContent,
  type CommPresetInUseDetails,
  type CommPresetRecord,
  type CommPresetVersion,
} from "../api";
import { PageContainer } from "../components/PageContainer";
import { ResizablePanel } from "../components/ResizablePanel";
import {
  CommContentChips,
  CommContentEditor,
} from "../components/CommContentEditor";
import { useConfirm } from "../components/Confirm";
import {
  CatalogExportButton,
  CatalogImportButton,
  catalogEntityFilename,
  uniqueImportedName,
} from "../components/CatalogTransfer";

const inputCls =
  "rounded-lg border border-surface-200 dark:border-surface-700 bg-white dark:bg-surface-800 px-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-accent-500/40";

// ------------------------------------------------------------------ //
// The 409 COMM_PRESET_IN_USE panel (molded on PoliciesView's
// PolicyInUsePanel): the server's normative binder list.
// ------------------------------------------------------------------ //
function PresetInUsePanel({
  details,
  onDismiss,
}: {
  details: CommPresetInUseDetails;
  onDismiss: () => void;
}) {
  return (
    <div
      className="mt-3 rounded-lg border border-red-300 dark:border-red-500/30 bg-red-50 dark:bg-red-900/10 p-3.5"
      data-testid="comm-preset-in-use-panel"
    >
      <div className="flex items-center gap-2 mb-2">
        <AlertTriangle size={14} className="text-red-500 dark:text-red-400 shrink-0" />
        <p className="text-xs font-semibold text-red-600 dark:text-red-300">
          Cannot delete — COMM_PRESET_IN_USE (409)
        </p>
      </div>
      <p className="text-xs text-red-600/90 dark:text-red-200/90 mb-2">
        Deleting this preset would orphan the communication binding of these
        agents. Detach it from them first (set them to inline or clear their
        style in the agent editor):
      </p>
      <ul className="text-xs text-surface-700 dark:text-surface-300 space-y-1 mb-3">
        {details.agents.map((agentId) => (
          <li key={agentId} className="flex items-center gap-2">
            <span className="w-1 h-1 rounded-full bg-red-400 shrink-0" />
            <span className="font-mono">{agentId}</span>
            <span className="text-surface-500 dark:text-surface-400">
              — still binds this preset
            </span>
          </li>
        ))}
      </ul>
      <button className="btn btn-secondary !py-1 text-xs" onClick={onDismiss}>
        Dismiss
      </button>
    </div>
  );
}

// ------------------------------------------------------------------ //
// Publish-a-new-version composer: the structured content editor + Publish.
// Publishes MAX+1 (append-only). An empty content {} is a legal version.
// ------------------------------------------------------------------ //
function PublishVersionForm({
  presetId,
  onPublished,
}: {
  presetId: string;
  onPublished: () => void | Promise<void>;
}) {
  const [content, setContent] = useState<CommContent>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const publish = async () => {
    setBusy(true);
    try {
      await api.publishCommPresetVersion(presetId, { content });
      setContent({});
      setError(null);
      await onPublished();
    } catch (exc) {
      setError((exc as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section
      className="mt-5 rounded-xl border border-dashed border-surface-300 dark:border-surface-700 p-4"
      data-testid="publish-comm-version-form"
    >
      <h3 className="text-sm font-semibold text-surface-700 dark:text-surface-300 mb-3">
        Publish a new version
      </h3>
      <CommContentEditor
        value={content}
        onChange={setContent}
        idPrefix={`publish-${presetId}`}
        testId="draft-comm-content"
      />
      {error && <p className="mt-2 mb-2 text-xs text-red-500">{error}</p>}
      <div className="flex items-center gap-2 mt-3">
        <button
          className="btn btn-primary"
          onClick={publish}
          disabled={busy}
          title="Publish the next immutable version (MAX+1)"
          data-testid="publish-comm-version"
        >
          <Plus size={14} /> Publish version
        </button>
        <span className="text-[10px] text-surface-400 dark:text-surface-500">
          Publishing with no dimensions set is allowed — an empty,
          non-directing version.
        </span>
      </div>
    </section>
  );
}

// ------------------------------------------------------------------ //
// The right inspector for one selected preset.
// ------------------------------------------------------------------ //
function PresetDetail({
  presetId,
  onClose,
  onChanged,
  onDeleted,
}: {
  presetId: string;
  onClose: () => void;
  onChanged: () => void;
  onDeleted: () => void;
}) {
  const { confirm, dialog } = useConfirm();
  const [record, setRecord] = useState<CommPresetRecord | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [inUse, setInUse] = useState<CommPresetInUseDetails | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api
      .commPreset(presetId)
      .then((rec) => {
        setRecord(rec);
        setName(rec.name);
        setDescription(rec.description ?? "");
        setInUse(null);
        setError(null);
      })
      .catch((exc) => setError((exc as Error).message));
  }, [presetId]);

  useEffect(() => {
    load();
  }, [load]);

  const dirty =
    record != null &&
    (name.trim() !== record.name ||
      description.trim() !== (record.description ?? ""));

  const saveHeader = async () => {
    try {
      await api.updateCommPreset(presetId, { name: name.trim(), description });
      setError(null);
      load();
      onChanged();
    } catch (exc) {
      setError((exc as Error).message);
    }
  };

  const remove = async () => {
    try {
      await api.deleteCommPreset(presetId);
      onDeleted();
    } catch (exc) {
      if (exc instanceof ApiError && exc.code === "COMM_PRESET_IN_USE") {
        setInUse(exc.details as CommPresetInUseDetails);
      } else {
        setError((exc as Error).message);
      }
    }
  };

  const versions = record?.versions ?? [];

  return (
    <div
      className="flex flex-col h-full min-h-0"
      data-testid="comm-preset-detail-body"
    >
      {dialog}
      <div className="shrink-0 flex items-center gap-2 mb-3">
        <h2 className="text-sm font-semibold text-surface-900 dark:text-surface-100 truncate">
          {record ? record.name : "Loading…"}
        </h2>
        {record && (
          <CatalogExportButton
            catalog="communication-presets"
            filename={catalogEntityFilename(
              "okto-nexus-communication-preset",
              record.name,
            )}
            className="ml-auto btn btn-secondary !py-1"
            title={`Export ${record.name} as JSON`}
            onExport={() => ({
              name: record.name,
              description: record.description,
              versions: (record.versions ?? []).map(({ content }) => ({ content })),
            })}
          />
        )}
        <button
          className="text-surface-400 hover:text-surface-700 dark:hover:text-surface-200"
          onClick={onClose}
          title="Close"
          data-testid="close-comm-preset-detail"
        >
          <X size={16} />
        </button>
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto pr-1">
        {error && <p className="mb-3 text-xs text-red-500">{error}</p>}

        {record && (
          <>
            {/* Editable header */}
            <section className="panel p-4">
              <div className="space-y-3">
                <label className="block">
                  <span className="text-[11px] uppercase tracking-wide text-surface-500 dark:text-surface-400">
                    Name
                  </span>
                  <input
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    className={`${inputCls} mt-1 block w-full`}
                    data-testid="comm-preset-name"
                  />
                </label>
                <label className="block">
                  <span className="text-[11px] uppercase tracking-wide text-surface-500 dark:text-surface-400">
                    Description
                  </span>
                  <input
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    placeholder="Optional"
                    className={`${inputCls} mt-1 block w-full`}
                    data-testid="comm-preset-description"
                  />
                </label>
              </div>
              <p className="text-[11px] text-surface-400 dark:text-surface-500 mt-3 font-mono">
                {presetId} · created{" "}
                {new Date(record.created_at).toLocaleString()}
              </p>
              <div className="flex items-center gap-2 mt-3">
                <button
                  className="btn btn-primary"
                  onClick={saveHeader}
                  disabled={!dirty || !name.trim()}
                  data-testid="save-comm-preset-header"
                >
                  Save
                </button>
                <button
                  className="btn btn-danger ml-auto"
                  onClick={() =>
                    confirm({
                      title: "Delete communication preset?",
                      body: (
                        <span>
                          <b className="font-mono">{record.name}</b> and its{" "}
                          {versions.length} version
                          {versions.length === 1 ? "" : "s"} will be removed.
                          This is refused if any agent still binds it.
                        </span>
                      ),
                      onConfirm: remove,
                    })
                  }
                  data-testid="delete-comm-preset"
                >
                  Delete
                </button>
              </div>
              {inUse && (
                <PresetInUsePanel
                  details={inUse}
                  onDismiss={() => setInUse(null)}
                />
              )}
            </section>

            {/* Version history */}
            <section className="mt-5" data-testid="comm-version-history">
              <div className="flex items-center gap-2 mb-2">
                <h3 className="text-xs font-semibold uppercase tracking-wide text-surface-500 dark:text-surface-400">
                  Version history
                </h3>
                <span className="chip bg-surface-200 text-surface-600 dark:bg-surface-700 dark:text-surface-300">
                  {versions.length}
                </span>
              </div>
              {versions.length === 0 ? (
                <p className="text-xs text-surface-400 dark:text-surface-500">
                  No versions published yet — publish the first one below.
                </p>
              ) : (
                <ul className="space-y-2">
                  {versions
                    .slice()
                    .reverse()
                    .map((version: CommPresetVersion) => (
                      <li
                        key={version.version}
                        className="rounded-lg border border-surface-200 dark:border-surface-700 p-3"
                        data-testid={`comm-version-${version.version}`}
                      >
                        <div className="flex items-center gap-2 mb-2">
                          <span className="chip bg-accent-100 text-accent-700 dark:bg-accent-900/40 dark:text-accent-300 font-mono">
                            @v{version.version}
                          </span>
                          {version.version === record.latest_version && (
                            <span className="chip bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300">
                              latest
                            </span>
                          )}
                          <span className="text-[11px] text-surface-400 dark:text-surface-500 ml-auto whitespace-nowrap">
                            {new Date(version.published_at).toLocaleString()}
                          </span>
                        </div>
                        <CommContentChips content={version.content} />
                      </li>
                    ))}
                </ul>
              )}
            </section>

            <PublishVersionForm
              presetId={presetId}
              onPublished={() => {
                load();
                onChanged();
              }}
            />
          </>
        )}
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ //
// The screen: master list (left) + inspector (right).
// ------------------------------------------------------------------ //
export function CommunicationView() {
  const [presets, setPresets] = useState<CommPresetRecord[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [draft, setDraft] = useState({ name: "", description: "" });
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(
    () =>
      api
        .commPresets()
        .then(({ items }) => {
          setPresets(items);
          setError(null);
        })
        .catch((exc) => setError((exc as Error).message)),
    [],
  );

  useEffect(() => {
    reload();
  }, [reload]);

  const create = async () => {
    const name = draft.name.trim();
    if (!name) return;
    try {
      const created = await api.createCommPreset({
        name,
        description: draft.description.trim() || undefined,
      });
      setDraft({ name: "", description: "" });
      setError(null);
      await reload();
      setSelectedId(created.preset_id);
    } catch (exc) {
      setError((exc as Error).message);
    }
  };

  return (
    <PageContainer
      width="bleed"
      scroll="none"
      className="flex"
      testId="communication-view"
    >
      <div className="flex-1 min-w-0 flex flex-col">
        {/* Header + new-preset form */}
        <div className="shrink-0 border-b border-surface-200/60 dark:border-surface-700/60 bg-white/80 dark:bg-surface-900/80 backdrop-blur-md px-4 py-3">
          <div className="flex items-center gap-2 mb-1">
            <h1 className="text-lg font-display font-semibold text-surface-900 dark:text-surface-100">
              Communication
            </h1>
            <span className="chip bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300">
              Operator-only
            </span>
            <span className="chip bg-surface-200 text-surface-600 dark:bg-surface-700 dark:text-surface-300">
              {presets.length} preset{presets.length === 1 ? "" : "s"}
            </span>
            <div className="ml-auto">
              <CatalogImportButton
                catalog="communication-presets"
                onImport={async (value) => {
                  const names = new Set(presets.map((preset) => preset.name.toLocaleLowerCase()));
                  if (!value || typeof value !== "object" || Array.isArray(value)) {
                    throw new Error("The communication preset export is invalid.");
                  }
                  const row = value as Record<string, unknown>;
                  if (typeof row.name !== "string") {
                    throw new Error("The communication preset must include a name.");
                  }
                  const versions = Array.isArray(row.versions) ? row.versions : [];
                  const contents = versions.map((versionValue) => {
                    if (
                      !versionValue ||
                      typeof versionValue !== "object" ||
                      Array.isArray(versionValue)
                    ) {
                      throw new Error("The communication preset contains an invalid version.");
                    }
                    const content = (versionValue as Record<string, unknown>).content;
                    if (!content || typeof content !== "object" || Array.isArray(content)) {
                      throw new Error("Each communication preset version must contain content.");
                    }
                    return content as CommContent;
                  });
                  const created = await api.createCommPreset({
                    name: uniqueImportedName(row.name, names),
                    description:
                      typeof row.description === "string" ? row.description : undefined,
                  });
                  for (const content of contents) {
                    await api.publishCommPresetVersion(created.preset_id, { content });
                  }
                  await reload();
                  setSelectedId(created.preset_id);
                }}
              />
            </div>
          </div>
          <p className="text-xs text-surface-500 dark:text-surface-400 mb-3">
            Named, versioned communication <b>styles</b> — how an agent should
            communicate (tone, format, language, verbosity, structure, notes).
            Bind one to an agent (in the Agents screen) and it appears on that
            agent's <code className="font-mono">whoami</code> only. Presets are
            reusable; an agent may instead carry an inline style of its own.
          </p>
          <div className="flex flex-wrap items-end gap-2">
            <label className="block">
              <span className="text-[10px] uppercase tracking-wide text-surface-400 dark:text-surface-500">
                Name
              </span>
              <input
                value={draft.name}
                onChange={(e) => setDraft({ ...draft, name: e.target.value })}
                onKeyDown={(e) => e.key === "Enter" && create()}
                placeholder="e.g. Concise"
                className={`${inputCls} mt-1 block w-48`}
                data-testid="new-comm-preset-name"
              />
            </label>
            <label className="block flex-1 min-w-40">
              <span className="text-[10px] uppercase tracking-wide text-surface-400 dark:text-surface-500">
                Description (optional)
              </span>
              <input
                value={draft.description}
                onChange={(e) =>
                  setDraft({ ...draft, description: e.target.value })
                }
                placeholder="What this style is for"
                className={`${inputCls} mt-1 block w-full`}
                data-testid="new-comm-preset-description"
              />
            </label>
            <button
              className="btn btn-primary"
              onClick={create}
              disabled={!draft.name.trim()}
              data-testid="create-comm-preset"
            >
              <Plus size={14} /> New preset
            </button>
          </div>
          {error && <p className="mt-2 text-xs text-red-500">{error}</p>}
        </div>

        {/* Preset list */}
        <div
          className="flex-1 overflow-y-auto px-4 py-3"
          data-testid="comm-presets-list"
        >
          {presets.length === 0 ? (
            <p className="text-xs text-surface-400 dark:text-surface-500">
              No communication presets yet — create the first one above.
            </p>
          ) : (
            <div className="space-y-1.5">
              {presets.map((preset) => (
                <div
                  key={preset.preset_id}
                  className={`w-full rounded-lg border flex items-start transition-colors ${
                    selectedId === preset.preset_id
                      ? "border-accent-300 dark:border-accent-700 bg-accent-50 dark:bg-accent-900/20"
                      : "border-surface-200 dark:border-surface-700 hover:bg-surface-50 dark:hover:bg-surface-800/50"
                  }`}
                  data-testid={`comm-preset-${preset.preset_id}`}
                >
                  <button
                    onClick={() => setSelectedId(preset.preset_id)}
                    className="min-w-0 flex-1 text-left px-3 py-2"
                  >
                    <div className="flex items-center gap-2">
                      <MessageSquare
                        size={14}
                        className="shrink-0 text-surface-400 dark:text-surface-500"
                      />
                      <span className="text-sm font-semibold text-surface-900 dark:text-surface-100 truncate">
                        {preset.name}
                      </span>
                      {preset.latest_version === 0 ? (
                        <span className="chip bg-surface-200 text-surface-500 dark:bg-surface-700 dark:text-surface-400">
                          no versions
                        </span>
                      ) : (
                        <span className="chip bg-accent-100 text-accent-700 dark:bg-accent-900/40 dark:text-accent-300 font-mono">
                          @v{preset.latest_version}
                        </span>
                      )}
                    </div>
                    {preset.description && (
                      <p className="text-xs text-surface-500 dark:text-surface-400 mt-0.5 truncate">
                        {preset.description}
                      </p>
                    )}
                  </button>
                  <CatalogExportButton
                    catalog="communication-presets"
                    filename={catalogEntityFilename(
                      "okto-nexus-communication-preset",
                      preset.name,
                    )}
                    className="btn btn-secondary !px-2 !py-1 !text-[10px] shrink-0 m-2 ml-0"
                    label="Export JSON"
                    title={`Export ${preset.name} as JSON`}
                    testId={`export-comm-preset-${preset.preset_id}`}
                    onExport={async () => {
                      const record = await api.commPreset(preset.preset_id);
                      return {
                        name: record.name,
                        description: record.description,
                        versions: (record.versions ?? []).map(({ content }) => ({ content })),
                      };
                    }}
                  />
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {selectedId && (
        <ResizablePanel storageKey="comm-preset-detail" testId="comm-preset-detail">
          <PresetDetail
            key={selectedId}
            presetId={selectedId}
            onClose={() => setSelectedId(null)}
            onChanged={reload}
            onDeleted={() => {
              setSelectedId(null);
              reload();
            }}
          />
        </ResizablePanel>
      )}
    </PageContainer>
  );
}
