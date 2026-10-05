import { ConfigurationHelp } from './ConfigurationHelp';
import { harnessFieldValues, harnessSelectionError } from '../harnessConfiguration';
import type { HarnessConfiguration } from '../runtimeApi';

const help: Record<string,string> = {
  model:'Model used by new sessions. Availability depends on the installation and account.',
  effort:'Reasoning or thinking effort for the selected model.', provider:'Provider that supplies the selected model.',
  approval_policy:'Native harness approval policy for commands and tools. Nexus tool access is configured separately.',
  permission_mode:'Native Claude permission mode. Nexus tool access is configured separately.',
  sandbox:'Native Codex filesystem and network restrictions.',
  user_input:'Allows structured questions. Answers are routed through the conversation participant.',
};
export function HarnessPreferenceFields({schema, values, onChange}: {schema: HarnessConfiguration;
  values: Record<string,string>; onChange: (values: Record<string,string>) => void}) {
  const error = harnessSelectionError(schema, values);
  const required = (field: HarnessConfiguration['parameters'][number]) => !!schema.constraints?.[field.name] &&
    field.default_source === 'core_adapter' && !harnessFieldValues(schema, field.name, values).includes(String(field.default));
  const change = (key: string, value: string) => {
    const next = {...values}; if (value) next[key] = value; else delete next[key]; onChange(next);
  };
  return <section aria-label="Harness settings" className="space-y-3">
    <h5 className="font-semibold">Model and native behavior</h5>
    <div className="grid md:grid-cols-2 gap-3">{schema.parameters.filter(p => p.core_applies).map(field =>
      <label key={field.name}>{field.label} <span className="text-surface-500">{required(field) ? 'Required by policy' : 'Optional'}</span>
        <ConfigurationHelp label={field.label}>{help[field.name] || 'Leave blank to use the harness default.'}</ConfigurationHelp>
        {field.type === 'enum' ? <select aria-label={field.label} className="block w-full rounded border p-2 bg-white dark:bg-surface-800"
          value={values[field.name] || ''} onChange={e => change(field.name,e.target.value)}>
          <option value="">Default{field.default != null ? ` (${String(field.default)})` : ' from harness'}</option>
          {!!values[field.name] && !harnessFieldValues(schema,field.name,values).includes(values[field.name]) && <option value={values[field.name]}>{values[field.name]} (unavailable)</option>}
          {harnessFieldValues(schema,field.name,values).map(v => <option key={v}>{v}</option>)}
        </select> : <input aria-label={field.label} className="block w-full rounded border p-2 bg-white dark:bg-surface-800"
          value={values[field.name] || ''} placeholder="Harness default" maxLength={200} onChange={e => change(field.name,e.target.value)} />}
      </label>)}</div>{error && <p role="alert">{error}</p>}
  </section>;
}
