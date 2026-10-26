import { useState } from "react";
import { runtimeApi } from "../runtimeApi";

export function RevalidateBindings({onDone}: {onDone: () => void}) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const run = async () => {
    setBusy(true); setError(""); setMessage("");
    try {
      const result = await runtimeApi.revalidateBindings();
      const open = result.bindings.length - result.revalidated - result.already_current;
      setMessage(`${result.revalidated} revalidated, ${result.already_current} already current, ${open} need another action.`);
      onDone();
    } catch (failure) { setError(String(failure)); }
    finally { setBusy(false); }
  };
  return <div data-testid="revalidate-bindings" className="space-y-1">
    <button className="btn btn-secondary" disabled={busy} onClick={() => void run()}>Revalidate all bindings</button>
    <p className="text-xs">Operator only. Accept the current installation for every binding after a harness update. This does not change grants or sessions.</p>
    {message && <p role="status">{message}</p>}
    {error && <p role="alert">{error}</p>}
  </div>;
}
