import { useEffect, useState } from "react";
import { api, type RuntimeUpdatePolicy as UpdatePolicy } from "../api";

type Choice = "" | "review" | "follow";

export function RuntimeUpdatePolicy({endpoint, onUpdated}: {endpoint: string; onUpdated?: () => void}) {
  const [policy, setPolicy] = useState<UpdatePolicy | null>(null);
  const [choice, setChoice] = useState<Choice>("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let active = true;
    setPolicy(null); setError("");
    api.runtimeUpdatePolicy(endpoint).then(result => {
      if (active) { setPolicy(result); setChoice(result.policy ?? ""); }
    }).catch(failure => { if (active) setError(failure instanceof Error ? failure.message : String(failure)); });
    return () => { active = false; };
  }, [endpoint, revision]);
  return <section aria-label="Runtime update policy" className="space-y-2 border-t pt-3">
    <h5 className="font-semibold">Runtime updates</h5>
    <label className="block">Update policy
      <select aria-label="Update policy" className="block rounded border p-2 bg-white dark:bg-surface-800" value={choice}
        disabled={busy || !policy} onChange={event => { setChoice(event.target.value as Choice); setNotice(""); }}>
        <option value="">{policy ? `Inherit (hub: ${policy.hub_policy})` : "Inherit"}</option>
        <option value="review">review</option>
        <option value="follow">follow</option>
      </select>
    </label>
    {policy && <p data-testid="update-policy-effective" className="text-xs">Effective: {policy.effective_policy} (source: {policy.policy_source}). Review holds a newer build until you accept it. Follow adopts one newer build by itself.</p>}
    <button className="btn btn-secondary" disabled={busy || !policy || choice === (policy.policy ?? "")} onClick={async () => {
      if (!policy) return;
      setBusy(true); setError(""); setNotice("");
      try {
        const result = await api.saveRuntimeUpdatePolicy(endpoint, {expected_revision: policy.revision, policy: choice === "" ? null : choice});
        setPolicy(result); setChoice(result.policy ?? ""); setNotice("Update policy saved."); onUpdated?.();
      } catch (failure) { setError(failure instanceof Error ? failure.message : String(failure)); }
      finally { setBusy(false); }
    }}>Save update policy</button>
    <button className="btn btn-secondary" disabled={busy} onClick={() => setRevision(value => value + 1)}>Reload update policy</button>
    {notice && <p role="status">{notice}</p>}{error && <p role="alert">{error}</p>}
  </section>;
}
