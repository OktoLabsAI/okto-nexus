import { useEffect, useRef, useState } from "react";
import { ApiError } from "../api";
import { runtimeApi, type LocalPreparationRequest, type RuntimeChoice } from "../runtimeApi";

const inputClass = "block w-full rounded border p-2 dark:bg-surface-800";

export function EmbeddedPreparation({agentId, executorId, hostLabel, workspaceId, workspaceLabel,
  inventoryRevision, choice, onPrepared, beforePrepare}: {
  agentId: string; executorId: string; hostLabel: string; workspaceId: string; workspaceLabel: string;
  inventoryRevision: string; choice: RuntimeChoice; onPrepared: (workspaceId: string) => void;
  beforePrepare?: () => Promise<void>;
}) {
  const storageKey = "okto-nexus:r4-local-preparation:" + JSON.stringify([
    agentId, executorId, workspaceId, choice.adapter_id, choice.candidate_ref, inventoryRevision,
  ]);
  const [saved] = useState(() => {
    try {
      const raw = sessionStorage.getItem(storageKey);
      if (!raw) return {request: null, error: ""};
      const request = JSON.parse(raw) as LocalPreparationRequest;
      if (request.agent_id !== agentId || request.adapter_id !== choice.adapter_id ||
          request.candidate_ref !== choice.candidate_ref || request.inventory_revision !== inventoryRevision ||
          request.workspace_id !== (workspaceId || null) || request.approved !== true ||
          typeof request.client_intent_id !== "string" || typeof request.local_consent_id !== "string" ||
          typeof request.workspace_root !== "string" || typeof request.workspace_label !== "string" ||
          (request.provider_home !== null && typeof request.provider_home !== "string") ||
          !request.secret_bindings || typeof request.secret_bindings !== "object") {
        throw new Error("The saved preparation does not match this selection. Review it before continuing.");
      }
      return {request, error: ""};
    } catch (failure) { return {request: null, error: String(failure)}; }
  });
  const [pending, setPending] = useState<LocalPreparationRequest | null>(saved.request);
  const [root, setRoot] = useState(saved.request?.workspace_root || "");
  const [home, setHome] = useState(saved.request?.provider_home || "");
  const [label, setLabel] = useState(saved.request?.workspace_label || workspaceLabel);
  const [references, setReferences] = useState(saved.request
    ? Object.entries(saved.request.secret_bindings).map(([name, ref]) => `${name}=${ref}`).join("\n") : "");
  const [approved, setApproved] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(saved.error);
  const runtimeSettings: Record<string, {name: string; home: string; credential: string}> = {
    codex_app_server: {name: 'Codex', home: 'The approved home supplies .codex state and login. CODEX_HOME is set to its .codex directory.', credential: 'OPENAI_API_KEY=vault:provider-key'},
    claude_stream: {name: 'Claude Code', home: 'Use the home directory containing the Claude Code login you want this agent to use.', credential: 'ANTHROPIC_API_KEY=vault:provider-key'},
    pi_rpc: {name: 'Pi', home: 'Use the home directory containing the Pi settings for the selected provider.', credential: 'OPENAI_API_KEY=vault:provider-key'},
  };
  const settings = runtimeSettings[choice.adapter_id];
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);

  const submit = async () => {
    setBusy(true); setError("");
    try {
      let request = pending;
      if (!request) {
        if (!approved || !root.trim() || !choice.candidate_ref) throw new Error("Review and approve the local folders first.");
        const secretBindings: Record<string, string> = Object.create(null);
        for (const line of references.split("\n").filter(line => line.trim())) {
          const match = /^([A-Za-z_][A-Za-z0-9_]{0,127})=((?:vault|provider):[^\r\n\0]+)$/.exec(line.trim());
          if (!match || !match[2].split(":").slice(1).join(":").trim() ||
              /nxs_|nxsept_|nxc4_|nxt4_/.test(match[2]) || match[2].length > 256 || match[1] in secretBindings) {
            throw new Error("Use one unique NAME=vault:reference or NAME=provider:reference per line. Do not enter secret values.");
          }
          secretBindings[match[1]] = match[2];
        }
        if (Object.keys(secretBindings).length > 64) throw new Error("At most 64 protected references are allowed.");
        const id = "ui_" + Array.from(crypto.getRandomValues(new Uint8Array(16)), byte => byte.toString(16).padStart(2, "0")).join("");
        request = {client_intent_id: id, local_consent_id: id, approved: true,
          agent_id: agentId, adapter_id: choice.adapter_id, candidate_ref: choice.candidate_ref,
          inventory_revision: inventoryRevision, workspace_id: workspaceId || null,
          workspace_label: workspaceId ? "" : label.trim(), workspace_root: root.trim(), provider_home: home.trim() || null,
          secret_bindings: secretBindings};
        // Persist before any request. Lost responses and tab reload retain the
        // same consent, scope and body; no credentials are stored here.
        sessionStorage.setItem(storageKey, JSON.stringify(request));
        setPending(request);
      }
      await beforePrepare?.();
      const result = await runtimeApi.prepareLocal(executorId, request);
      if (result.executor_id !== executorId || result.agent_id !== agentId ||
          result.inventory_revision !== inventoryRevision || !result.realization_ref || !result.workspace_id ||
          (workspaceId && result.workspace_id !== workspaceId)) {
        throw new Error("The returned preparation does not match this selection.");
      }
      if (mounted.current) onPrepared(result.workspace_id);
    } catch (failure) {
      // Only a first, explicitly rejected request can be edited. A retry may
      // follow a lost successful reply, so keep its original identity/body.
      if (!pending && failure instanceof ApiError && failure.status >= 400 && failure.status < 500) {
        try {
          sessionStorage.removeItem(storageKey);
          if (mounted.current) { setPending(null); setApproved(false); }
        } catch { /* Retain the recorded request if storage cannot be updated. */ }
      }
      if (mounted.current) setError(String(failure));
    }
    finally { if (mounted.current) setBusy(false); }
  };

  return <section aria-label="Local workspace preparation" className="space-y-3 rounded border p-3">
    <h5 className="font-semibold">{settings?.name || choice.adapter_id} configuration</h5>
    <p>Prepare folders on {hostLabel}.</p>
    <p>These paths belong to the computer running this Nexus Server, even if your browser is on another computer. Select existing absolute directories.</p>
    <fieldset disabled={busy || pending !== null || !!saved.error} className="space-y-2">
      <label className="block">Workspace directory<input aria-label="Workspace directory" className={inputClass} value={root} maxLength={4096} onChange={event => setRoot(event.target.value)} /></label>
      {!workspaceId && <label className="block">New workspace name<input aria-label="New workspace name" className={inputClass} value={label} maxLength={160} onChange={event => setLabel(event.target.value)} /></label>}
      {workspaceId && <p>Workspace: {workspaceLabel || workspaceId}</p>}
      <label className="block">Provider home directory (optional)<input aria-label="Provider home directory" className={inputClass} value={home} maxLength={4096} onChange={event => setHome(event.target.value)} /></label>
      <p>Use an existing provider home for its login, or protected references configured on this host. A blank home does not configure a login directory.</p>
      {settings && <p>{settings.home}</p>}
      <label className="block">Protected credential references (optional)<textarea aria-label="Protected credential references" className={inputClass} value={references} maxLength={25000} rows={2} placeholder={settings?.credential} onChange={event => setReferences(event.target.value)} /></label>
      <p>Enter reference names only, never API keys or tokens.</p>
      <label className="block"><input type="checkbox" checked={approved} onChange={event => setApproved(event.target.checked)} /> I approve these folders and protected references for this agent and installation.</label>
    </fieldset>
    <p>Preparation records local configuration. Connection approval and permission to execute remain separate steps.</p>
    {pending && <p role="status">This preparation request was recorded. Retry the same request to confirm its result; its folders and consent remain unchanged.</p>}
    <button className="btn btn-primary" disabled={busy || !!saved.error || (!pending && (!approved || !root.trim() || (!workspaceId && (!label.trim() || /[\\/:]/.test(label)))))}
      onClick={() => void submit()}>{pending ? "Retry the same preparation" : "Approve local preparation"}</button>
    {error && <p role="alert">{error}</p>}
  </section>;
}
