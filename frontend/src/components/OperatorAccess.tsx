import { useSettingsDraft } from './SettingsDrafts';
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
  const dirty = !!status && (username !== (status.username || 'operator') || !!password || !!confirm || !!current);
  const valid = !!status && !busy && !!username.trim() && password.length >= 12 && password.length <= 1024 && password === confirm && (status.local || !!current);
  const save = async () => {
      if (password !== confirm) { setMessage("Passwords do not match."); return false; }
      setBusy(true); setMessage("");
      try {
        await api.operatorAccount(username.trim(), password, current);
        setPassword(""); setConfirm(""); setCurrent("");
        setMessage("Operator access saved. Existing remote sessions have been signed out.");
        setStatus(await api.operatorStatus());
        window.dispatchEvent(new Event("nexus-auth-expired"));
        return true;
      } catch (exc) { setMessage((exc as Error).message); return false; }
      finally { setBusy(false); }
    };
  const managed = useSettingsDraft('operator', {dirty, valid: !dirty || valid, save});
  const field = "block w-full rounded-lg border border-surface-300 dark:border-surface-600 bg-white dark:bg-surface-800 px-3 py-2 text-sm text-surface-900 dark:text-surface-100 outline-none focus:border-accent-500 focus:ring-2 focus:ring-accent-500/20 disabled:opacity-50";
  const label = "block space-y-1.5 text-xs font-medium text-surface-700 dark:text-surface-200";
  const mismatch = !!confirm && password !== confirm;
  return <section className="panel p-5 space-y-3">
    <h2 className="font-display font-semibold text-sm">Operator access</h2>
    <p className="text-xs text-surface-500">Local access needs no login. Configure a separate account for the remote dashboard.</p>
    <div><span className="inline-flex rounded-full bg-surface-100 dark:bg-surface-800 px-2.5 py-1 text-xs text-surface-600 dark:text-surface-300">{!status ? 'Loading account…' : status.configured ? "Remote sign-in configured" : "Remote sign-in not configured"}</span></div>
    <form className="space-y-4 pt-2" onSubmit={event => {event.preventDefault(); if (!managed) void save();}}>
      <fieldset disabled={busy || !status} className="grid min-w-0 grid-cols-1 gap-x-6 gap-y-4 md:grid-cols-2">
        <label className={label}><span>Username</span><input required maxLength={80} autoComplete="username" value={username} onChange={e => setUsername(e.target.value)} className={field}/></label>
        {!status?.local ? <label className={label}><span>Current password</span><input required type="password" autoComplete="current-password" value={current} onChange={e => setCurrent(e.target.value)} className={field}/></label> : <div className="hidden md:block" />}
        <label className={label}><span>New password</span><input required minLength={12} maxLength={1024} type="password" autoComplete="new-password" aria-describedby="operator-password-help" value={password} onChange={e => setPassword(e.target.value)} className={field}/><span id="operator-password-help" className="block font-normal text-surface-500">Use at least 12 characters.</span></label>
        <label className={label}><span>Confirm password</span><input required minLength={12} maxLength={1024} type="password" autoComplete="new-password" aria-invalid={mismatch} aria-describedby={mismatch ? 'operator-password-error' : undefined} value={confirm} onChange={e => setConfirm(e.target.value)} className={field}/>{mismatch && <span id="operator-password-error" role="alert" className="block font-normal text-red-500">Passwords do not match.</span>}</label>
      </fieldset>
      <p className="border-t border-surface-200 dark:border-surface-700 pt-3 text-xs text-surface-500">Changing these credentials signs out existing remote sessions.{managed && ' Apply your edits with Save changes below.'}</p>
      {message && <p role="status" className="text-xs">{message}</p>}
      {!managed && <button className="btn btn-primary" disabled={busy || !status}>{busy ? "Saving…" : "Save operator access"}</button>}
    </form>
  </section>;
}
