import { useEffect, useRef, useState } from "react";
import { runtimeApi } from "../runtimeApi";

export function LocalInstallationCheck({agentId, executorId, adapterId, candidateRef, inventoryRevision, onChecked, beforeCheck}: {
  agentId: string; executorId: string; adapterId: string; candidateRef: string;
  inventoryRevision: string; onChecked: () => void;
  beforeCheck?: () => Promise<void>;
}) {
  const [approved, setApproved] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [checked, setChecked] = useState("");
  const active = useRef(true);
  useEffect(() => { active.current = true; return () => { active.current = false; }; }, []);
  async function check() {
    if (!approved || busy) return;
    setBusy(true); setError(""); setChecked("");
    try {
      await beforeCheck?.();
      const result = await runtimeApi.checkLocalInstallation(executorId, {
        agent_id: agentId, adapter_id: adapterId, candidate_ref: candidateRef,
        inventory_revision: inventoryRevision, approved: true,
      });
      if (active.current) { setChecked(result.version); onChecked(); }
    } catch (failure) {
      if (active.current) setError(String(failure) + " The version check may have run. Refresh inventory before checking again.");
    } finally { if (active.current) { setBusy(false); setApproved(false); } }
  }
  return <section aria-label="Local installation version check" className="space-y-2 rounded border p-3">
    <p>Check this installation before preparing its workspace. This runs its version command on the Server in a temporary directory, without provider credentials.</p>
    <label className="block"><input type="checkbox" checked={approved} disabled={busy}
      onChange={event => setApproved(event.target.checked)} /> I approve selecting this exact local installation and running its version check.</label>
    <button className="btn btn-secondary" disabled={busy || !approved} onClick={() => void check()}>
      {busy ? "Checking version…" : "Check installation version"}
    </button>
    {checked && <p role="status">Version observed: {checked}. Runtime approval is still separate.</p>}
    {error && <p role="alert">{error}</p>}
  </section>;
}
