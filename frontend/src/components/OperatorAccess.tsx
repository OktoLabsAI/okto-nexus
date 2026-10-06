import { useEffect, useState } from "react";
import { api, type OperatorStatus } from "../api";

export function OperatorAccess() {
  const [status, setStatus] = useState<OperatorStatus | null>(null);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [current, setCurrent] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  useEffect(() => { api.operatorStatus().then(value => {
    setStatus(value); setUsername(value.username || "operator");
  }).catch(exc => setMessage((exc as Error).message)); }, []);
  const field = "w-full border rounded-lg p-2 mt-1 bg-transparent";
  return <section className="panel p-5 space-y-3">
    <h2 className="font-display font-semibold text-sm">Operator access</h2>
    <p className="text-xs text-surface-500">Local access needs no login. Configure a separate account for the remote dashboard.</p>
    <p className="text-xs">{status?.configured ? "Remote sign-in configured" : "Remote sign-in not configured"}</p>
    <form className="space-y-3" onSubmit={async event => {
      event.preventDefault();
      if (password !== confirm) { setMessage("Passwords do not match."); return; }
      setBusy(true); setMessage("");
      try {
        await api.operatorAccount(username.trim(), password, current);
        setPassword(""); setConfirm(""); setCurrent("");
        setMessage("Operator access saved. Existing remote sessions have been signed out.");
        setStatus(await api.operatorStatus());
        window.dispatchEvent(new Event("nexus-auth-expired"));
      } catch (exc) { setMessage((exc as Error).message); }
      finally { setBusy(false); }
    }}>
      <label className="block text-sm">Username<input required maxLength={80} autoComplete="username" value={username} onChange={e => setUsername(e.target.value)} className={field}/></label>
      {!status?.local && <label className="block text-sm">Current password<input required type="password" autoComplete="current-password" value={current} onChange={e => setCurrent(e.target.value)} className={field}/></label>}
      <label className="block text-sm">New password<input required minLength={12} maxLength={1024} type="password" autoComplete="new-password" title="At least 12 characters. Changing the password signs out all remote sessions." value={password} onChange={e => setPassword(e.target.value)} className={field}/></label>
      <label className="block text-sm">Confirm password<input required minLength={12} type="password" autoComplete="new-password" value={confirm} onChange={e => setConfirm(e.target.value)} className={field}/></label>
      {message && <p role="status" className="text-sm">{message}</p>}
      <button className="btn btn-primary" disabled={busy || !status}>{busy ? "Saving…" : "Save operator access"}</button>
    </form>
  </section>;
}
