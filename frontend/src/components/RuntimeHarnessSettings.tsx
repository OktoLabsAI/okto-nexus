import { ConfigurationHelp } from './ConfigurationHelp';
import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { HarnessConfiguration } from "../runtimeApi";
import { harnessFieldValues, harnessSelectionError, parseHarnessConfigurationFile, harnessConfigurationFile } from '../harnessConfiguration';

export function RuntimeHarnessSettings({endpoint, schema, onUpdated}: {
  endpoint: string; schema: HarnessConfiguration; onUpdated: () => void;
}) {
  const [saved, setSaved] = useState<{revision: number; settings: Record<string,string>} | null>(null);
  const [values, setValues] = useState<Record<string,string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [reload, setReload] = useState(0);
  useEffect(() => {
    let live = true;
    setSaved(null); setError(""); setNotice(""); setValues({});
    api.runtimeHarnessSettings(endpoint).then(result => {if(live){setSaved(result);setValues(result.settings);}})
      .catch(reason => {if(live) setError(String(reason));});
    return () => {live = false;};
  }, [endpoint, reload]);
  const fileInput = useRef<HTMLInputElement>(null);
  const help: Record<string,string> = {
    model: 'Model used by new sessions. Available models depend on the installation and account.',
    effort: 'Reasoning or thinking effort. Available levels depend on the selected model and harness.',
    provider: 'Provider that supplies the model. Select it when the same model name exists under multiple providers.',
    approval_policy: 'Native harness approval policy for commands and tools. Nexus permissions remain separate.',
    permission_mode: 'Claude native permission mode. This does not change Nexus agent permissions.',
    sandbox: 'Native Codex filesystem and network restrictions for the session.',
    user_input: 'Allows Codex to ask structured questions in default mode. Answers go through the conversation participant.',
  };
  const required = (field: HarnessConfiguration['parameters'][number]) => !!schema.constraints?.[field.name] &&
    field.default_source === 'core_adapter' && !harnessFieldValues(schema, field.name, values).includes(String(field.default));
  const selectionError = harnessSelectionError(schema, values);
  return <section aria-label="Harness settings" className="space-y-3">
    <h5 className="font-semibold">Model and native behavior <ConfigurationHelp label="Harness settings">Defaults are used for omitted parameters. Close existing sessions before saving. Changes invalidate execution permission and apply to new sessions.</ConfigurationHelp></h5>

    <div className="flex flex-wrap items-center gap-2">
      <button className="btn btn-secondary" disabled={busy || !saved} onClick={() => fileInput.current?.click()}>Import JSON</button>
      <ConfigurationHelp label="Import JSON">Optional. Load a settings file for this harness, review its values, then save. Importing does not start a session.</ConfigurationHelp>
      <input ref={fileInput} className="hidden" type="file" accept=".json,application/json" aria-label="Import settings from JSON"
        disabled={busy || !saved} onChange={async event => {
          const input = event.currentTarget;
          const file = input.files?.[0];
          input.value = '';
          if (!file) return;
          setError(''); setNotice('');
          try {
            if (file.size > 65536) throw new Error('The file must be 64 KiB or smaller.');
            setValues(parseHarnessConfigurationFile(await file.text(), schema));
            setNotice('File loaded. Review the values, then save the settings.');
          } catch (reason) {setError(String(reason));}
        }} />
    <button className="btn btn-secondary" disabled={busy || !saved || !!selectionError} onClick={() => {
      const url = URL.createObjectURL(new Blob([harnessConfigurationFile(schema.adapter_id, values)], {type:'application/json'}));
      const link = document.createElement('a'); link.href = url; link.download = `${schema.adapter_id}.harness.json`;
      link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    }}>Export JSON</button>
    </div>
    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
    {schema.parameters.filter(p => p.core_applies).map(field => <label key={field.name} className="block">
      {field.label} <span className="text-xs text-surface-500">{required(field) ? "Required by policy" : "Optional"}</span><ConfigurationHelp label={field.label}>{help[field.name] || "Leave blank to use the harness default."}</ConfigurationHelp>
      {field.type === 'enum' ? <select aria-label={field.label} className="block w-full border rounded p-2 bg-white dark:bg-surface-800"
        disabled={busy || !saved} value={values[field.name] || ""} onChange={e => setValues(old => ({...old,[field.name]: e.target.value}))}>
        <option value="">Default{field.default != null ? ` (${String(field.default)})` : " from harness"}</option>
        {!!values[field.name] && !harnessFieldValues(schema, field.name, values).includes(values[field.name]) &&
          <option value={values[field.name]}>{values[field.name]} (unavailable for this selection)</option>}
        {harnessFieldValues(schema, field.name, values).map(value => <option key={value} value={value}>{value}</option>)}
      </select> : <input aria-label={field.label} className="block w-full border rounded p-2 bg-white dark:bg-surface-800" maxLength={200}
        placeholder="Harness default" disabled={busy || !saved} value={values[field.name] || ""}
        onChange={e => setValues(old => ({...old,[field.name]: e.target.value}))} />}
    </label>)}
    </div>

    {selectionError && <p role="alert">{selectionError}</p>}
    <button className="btn btn-secondary" disabled={busy || !saved || !!selectionError} onClick={async () => {
      if(!saved) return;
      setBusy(true); setError(""); setNotice("");
      try {
        const settings = Object.fromEntries(Object.entries(values).filter(([,value]) => value !== ""));
        const result = await api.saveRuntimeHarnessSettings(endpoint, {expected_revision:saved.revision,settings});
        setSaved(result);setValues(result.settings);setNotice("Settings saved. Authorize execution before starting a new session.");onUpdated();
      } catch(reason) {setError(String(reason));} finally {setBusy(false);}
    }}>Save harness settings</button>
    <button className="btn btn-secondary" disabled={busy} onClick={() => setReload(value => value + 1)}>Reload settings</button>
    {error && <p role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}
  </section>;
}
