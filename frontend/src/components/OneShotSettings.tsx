import { forwardRef, useEffect, useImperativeHandle, useState } from 'react';
import { api, type OneShotPolicy, type OneShotSettings as Settings } from '../api';
import { OneShotActivity } from './OneShotActivity';

const fields: Array<{key: Exclude<keyof Settings, 'overflow'>; label: string; min: number; max: number}> = [
  {key: 'max_parallel', label: 'Maximum parallel instances (0 = unlimited)', min: 0, max: 256},
  {key: 'warm_instances', label: 'Preinitialized instances', min: 0, max: 255},
  {key: 'queue_capacity', label: 'Maximum queued calls', min: 0, max: 10000},
  {key: 'queue_timeout_seconds', label: 'Queue timeout (seconds)', min: 1, max: 86400},
  {key: 'execution_timeout_seconds', label: 'Execution timeout (seconds)', min: 1, max: 604800},
];

export type OneShotSettingsHandle = {save: () => Promise<boolean>};
export const OneShotSettings = forwardRef<OneShotSettingsHandle, {agentId?: string; showActivity?: boolean; saveOnNext?: boolean; onPendingChange?: (pending: boolean) => void}>(function OneShotSettings({agentId, showActivity = true, saveOnNext = false, onPendingChange}, ref) {
  const [policy, setPolicy] = useState<OneShotPolicy | null>(null);
  const [values, setValues] = useState<Partial<Settings>>({});
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [reload, setReload] = useState(0);
  useEffect(() => {
    let live = true;
    setBusy(true); setPolicy(null); setError(''); setNotice('');
    api.oneShotPolicy(agentId).then(p => {if (live) {setPolicy(p); setValues(p.settings);}})
      .catch(e => {if (live) setError(String(e));}).finally(() => {if (live) setBusy(false);});
    return () => {live = false;};
  }, [agentId, reload]);
  const effective = policy ? {...policy.defaults, ...values} : null;
  const dirty = !!policy && [...fields.map(f => f.key), 'overflow' as const].some(key => values[key] !== policy.settings[key]);
  useEffect(() => () => {onPendingChange?.(false);}, [onPendingChange]);
  const invalid = effective && ((effective.max_parallel !== 0 && effective.warm_instances >= effective.max_parallel) || fields.some(
    f => !Number.isInteger(effective[f.key]) || effective[f.key] < f.min || effective[f.key] > f.max));
  useEffect(() => {onPendingChange?.(busy || !policy || !!invalid);}, [busy, policy, invalid, onPendingChange]);
  const save = async () => {
    if (busy || !policy || invalid) return false;
    if (!dirty) return true;
    setBusy(true); setError(''); setNotice('');
    try {
      const p = await api.saveOneShotPolicy({expected_revision: policy.revision, settings: values}, agentId);
      setPolicy(p); setValues(p.settings); setNotice('One-shot capacity saved.');
      return true;
    } catch (e) {setError(String(e)); return false;}
    finally {setBusy(false);}
  };
  useImperativeHandle(ref, () => ({save}));
  const inherit = (key: keyof Settings) => setValues(old => {const copy = {...old}; delete copy[key]; return copy;});
  return <section aria-label="One-shot capacity" className="space-y-3 border-t pt-3">
    <h4 className="font-semibold">One-shot capacity</h4>
    {saveOnNext && <p className="text-xs">Next saves these limits for this agent across its connections.</p>}
    <p className="text-xs text-surface-500">Each call uses a fresh session and closes after its final response. Starting, preinitialized, running and closing instances share the pool limit. Use 0 for unlimited pool capacity; host capacity still applies. Preinitialized instances must be fewer than a finite limit. Replenishment runs independently from ready sessions.</p>
    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
      {fields.map(f => <label className="block" key={f.key}>{f.label}
        {agentId && <span className="block text-xs"><input type="checkbox" checked={values[f.key] === undefined} disabled={busy || !policy}
          onChange={e => e.target.checked ? inherit(f.key) : setValues(old => ({...old, [f.key]: policy!.defaults[f.key]}))} /> Inherit global ({policy?.defaults[f.key]})</span>}
        <input aria-label={f.label} type="number" min={f.min} max={f.max} step={1}
          className="block w-full rounded border p-2 bg-white dark:bg-surface-800"
          disabled={busy || !policy || (!!agentId && values[f.key] === undefined)} value={values[f.key] ?? policy?.defaults[f.key] ?? ''}
          onChange={e => setValues(old => ({...old, [f.key]: e.target.valueAsNumber}))} />
      </label>)}
      <label>When at capacity<select aria-label="One-shot overflow" className="block w-full rounded border p-2 bg-white dark:bg-surface-800"
        disabled={busy || !policy} value={values.overflow ?? 'inherit'} onChange={e => e.target.value === 'inherit' ? inherit('overflow') : setValues(old => ({...old, overflow: e.target.value as Settings['overflow']}))}>
        {agentId && <option value="inherit">Inherit global ({policy?.defaults.overflow})</option>}
        <option value="queue">Queue within limits</option><option value="reject">Reject immediately</option>
      </select></label>
    </div>
    {invalid && <p role="alert">Use whole numbers within the limits. Preinitialized instances must be fewer than a finite maximum parallel limit.</p>}
    {!saveOnNext && <button className="btn btn-secondary" disabled={busy || !policy || !!invalid} onClick={() => void save()}>Save one-shot capacity</button>}
    <button className="btn btn-secondary ml-2" disabled={busy} onClick={() => setReload(n => n + 1)}>Reload capacity</button>
    {error && <p role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}
    {agentId && <OneShotActivity agentId={agentId} showCalls={showActivity} revision={policy?.revision} />}
  </section>;
});
