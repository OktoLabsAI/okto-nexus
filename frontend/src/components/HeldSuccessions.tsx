import { useCallback, useEffect, useState } from "react";
import { runtimeApi, type HeldSuccession } from "../runtimeApi";

const message = (failure: unknown) => failure instanceof Error ? failure.message : String(failure);

export function HeldSuccessions({onDone}: {onDone?: () => void}) {
  const [items, setItems] = useState<HeldSuccession[] | null>(null);
  const [busy, setBusy] = useState<number | null>(null);
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    try { setItems((await runtimeApi.heldSuccessions()).items); }
    catch (failure) { setError(message(failure)); setItems([]); }
  }, []);
  useEffect(() => { void load(); }, [load]);
  const accept = async (id: number) => {
    setBusy(id); setError("");
    try { await runtimeApi.acceptSuccession(id); onDone?.(); }
    catch (failure) { setError(message(failure)); }
    finally { setBusy(null); await load(); }
  };
  if (items === null || (items.length === 0 && !error)) return null;
  return <section data-testid="held-successions" aria-label="Held runtime updates" className="space-y-2">
    <h5 className="font-semibold">Runtime updates on hold</h5>
    <p className="text-xs">A newer build waits for your decision. Accept it to use it for these connections.</p>
    <ul className="space-y-2">{items.map(item => <li key={item.id} data-testid="held-succession" className="border rounded-lg p-3">
      <p className="font-medium">{item.agent_ids.join(", ") || "No agent"} · {item.adapter_id} · {item.executor_id}</p>
      <p>From {item.from_version ?? "unknown"} to {item.to_version ?? "unknown"}</p>
      <p className="text-xs">Reason: {item.reason}</p>
      <p className="text-xs">Held at {item.decided_at}</p>
      <button className="btn btn-secondary" disabled={busy !== null || !item.can_accept} onClick={() => void accept(item.id)}>Accept update</button>
      {!item.can_accept && <p className="text-xs">This update failed a trust rule. Rebind the agent instead.</p>}
    </li>)}</ul>
    {error && <p role="alert">{error}</p>}
  </section>;
}
