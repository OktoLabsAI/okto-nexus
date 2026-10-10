import type { MCPPreset } from '../api';

const inputClass = 'block w-full min-w-0 rounded border p-2 bg-white dark:bg-surface-800';

function MappingFields({label, value, onChange}: {label: string; value: Record<string, string>; onChange: (value: Record<string, string>) => void}) {
  const entries = Object.entries(value);
  return <fieldset className="space-y-2 min-w-0"><legend className="font-medium">{label}</legend>
    {entries.map(([key, item], index) => <div key={index} className="grid grid-cols-1 sm:grid-cols-[1fr_1fr_auto] gap-2">
      <input aria-label={`${label} name ${index + 1}`} className={inputClass} value={key} onChange={e => {
        if (entries.some(([name], i) => i !== index && name.toLowerCase() === e.target.value.toLowerCase())) {
          e.target.setCustomValidity('This name is already in use.'); e.target.reportValidity(); return;
        }
        e.target.setCustomValidity('');
        onChange(Object.fromEntries(entries.map((entry, i) => i === index ? [e.target.value, item] : entry)));
      }} />
      <input aria-label={`${label} value ${index + 1}`} className={inputClass} value={item}
        onChange={e => onChange({...value, [key]: e.target.value})} />
      <button type="button" className="btn btn-secondary" aria-label={`Remove ${label} ${index + 1}`}
        onClick={() => onChange(Object.fromEntries(entries.filter((_, i) => i !== index)))}>Remove</button>
    </div>)}
    <button type="button" className="btn btn-secondary" onClick={() => {
      let n = 1; while (`VARIABLE_${n}` in value) n++;
      onChange({...value, [`VARIABLE_${n}`]: ''});
    }}>Add {label.toLowerCase()}</button>
  </fieldset>;
}

export function parseMCPPreset(text: string): MCPPreset['servers'] {
  if (new TextEncoder().encode(text).length > 32768) throw new Error('MCP preset must be 32 KiB or smaller.');
  const value = JSON.parse(text);
  if (!Array.isArray(value) || value.some(server => !server || typeof server !== 'object' || Array.isArray(server)))
    throw new Error('Unable to read MCP servers. Reload the connection.');
  const names = new Set<string>();
  for (const server of value) {
    if (typeof server.name !== 'string' || !/^[A-Za-z][A-Za-z0-9_-]{0,63}$/.test(server.name) || /^nexus/i.test(server.name) || names.has(server.name.toLowerCase()))
      throw new Error('Each MCP needs a unique name starting with a letter. Use letters, numbers, hyphens or underscores; Nexus names are reserved.');
    names.add(server.name.toLowerCase());
    if (server.transport === 'stdio' && !server.command?.trim()) throw new Error(`${server.name}: enter a command.`);
    if (server.transport === 'http') {
      let url: URL;
      try {url = new URL(server.url);} catch {throw new Error(`${server.name}: enter an HTTP or HTTPS URL.`);}
      if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash)
        throw new Error(`${server.name}: use an HTTP(S) URL without credentials, query or fragment.`);
    }
    for (const field of ['env_refs', 'header_refs'])
      if (Object.values(server[field] ?? {}).some(ref => typeof ref !== 'string' || !/^(vault|provider):\S+/.test(ref)))
        throw new Error(`${server.name}: secret references must start with vault: or provider:.`);
    if (Object.keys(server.env ?? {}).some(key => key in (server.env_refs ?? {})))
      throw new Error(`${server.name}: an environment variable cannot also have a secret reference.`);
  }
  return value;
}

export function MCPPresetFields({value, onChange, remote = false}: {value: string; onChange: (text: string) => void; remote?: boolean}) {
  const servers = JSON.parse(value) as MCPPreset['servers'];
  const update = (index: number, changes: Record<string, unknown>) => onChange(JSON.stringify(servers.map((server, i) => i === index ? {...server, ...changes} : server)));
  let error = '';
  try {parseMCPPreset(value);} catch (reason) {error = String(reason);}
  const add = (transport: 'stdio' | 'http') => {
    let index = servers.length + 1;
    while (servers.some(server => server.name === `server${index}`)) index++;
    servers.push(transport === 'stdio'
      ? {name: `server${index}`, enabled: true, transport, command: '', args: [], env: {}, env_refs: {}}
      : {name: `server${index}`, enabled: true, transport, url: '', header_refs: {}});
    onChange(JSON.stringify(servers, null, 2));
  };
  return <section aria-label="Runtime MCP preset" className="space-y-3 border-t pt-3 min-w-0">
    <h5 className="font-semibold">MCP servers for this harness</h5>
    <p className="text-surface-500">Add the MCPs this agent needs in new runtime sessions. These work together with the harness global MCP inheritance setting. A matching name replaces an inherited server.</p>
    <p className="text-surface-500">Commands and paths run on the runtime host. Use secret references for credentials already authorized on that host. Nexus tools follow the agent permissions.</p>
    <div className="flex flex-wrap gap-2">
      <button type="button" className="btn btn-secondary" disabled={servers.length >= 32} onClick={() => add('stdio')}>Add stdio MCP</button>
      <button type="button" className="btn btn-secondary" disabled={servers.length >= 32} onClick={() => add('http')}>Add HTTP MCP</button>
    </div>
    {!servers.length && <p className="text-surface-500">No additional MCP servers configured.</p>}
    {servers.map((server, index) => <fieldset key={index} className="rounded-lg border p-3 space-y-3 min-w-0">
      <legend className="font-semibold px-1">MCP {index + 1} · {server.transport === 'http' ? 'HTTP' : 'Local command'}</legend>
      <div className="flex flex-wrap items-end gap-3">
        <label className="flex-1 min-w-0">Server name<input className={inputClass} value={String(server.name ?? '')} maxLength={64}
          onChange={e => update(index, {name: e.target.value})} /></label>
        <label className="py-2"><input type="checkbox" checked={server.enabled !== false} onChange={e => update(index, {enabled: e.target.checked})} /> Enabled</label>
        <button type="button" className="btn btn-secondary" aria-label={`Remove MCP ${index + 1}`} onClick={() => onChange(JSON.stringify(servers.filter((_, i) => i !== index)))}>Remove MCP</button>
      </div>
      <label className="block">Connection type<select className={inputClass} value={String(server.transport)} onChange={e => {
        const replacement = e.target.value === 'stdio' ? {command: '', args: [], env: {}, env_refs: {}} : {url: '', header_refs: {}};
        onChange(JSON.stringify(servers.map((item, i) => i === index ? {name: server.name, enabled: server.enabled, transport: e.target.value, ...replacement} : item)));
      }}><option value="stdio">Local command (stdio)</option><option value="http">HTTP server</option></select></label>
      {server.transport === 'stdio' ? <>
        <label className="block">Command<input className={inputClass} value={String(server.command ?? '')} placeholder="npx"
          onChange={e => update(index, {command: e.target.value})} /></label>
        <fieldset className="space-y-2"><legend>Arguments (in order)</legend>
          {(server.args as string[] ?? []).map((arg, i, args) => <div key={i} className="flex gap-2">
            <input aria-label={`Argument ${i + 1}`} className={inputClass} value={arg} onChange={e => update(index, {args: args.map((a, j) => j === i ? e.target.value : a)})} />
            <button type="button" className="btn btn-secondary" aria-label={`Remove argument ${i + 1}`} onClick={() => update(index, {args: args.filter((_, j) => j !== i)})}>Remove</button>
          </div>)}
          <button type="button" className="btn btn-secondary" onClick={() => update(index, {args: [...(server.args as string[] ?? []), '']})}>Add argument</button>
        </fieldset>
        <MappingFields label="Environment variables" value={server.env as Record<string, string> ?? {}} onChange={env => update(index, {env})} />
        <MappingFields label="Environment secret references" value={server.env_refs as Record<string, string> ?? {}} onChange={env_refs => update(index, {env_refs})} />
      </> : <>
        <label className="block">Server URL<input type="url" className={inputClass} value={String(server.url ?? '')} placeholder="https://example.com/mcp"
          onChange={e => update(index, {url: e.target.value})} /></label>
        <MappingFields label="Header secret references" value={server.header_refs as Record<string, string> ?? {}} onChange={header_refs => update(index, {header_refs})} />
      </>}
      <p className="text-surface-500">Use vault:name or provider:name for secret references. Disabling this server also disables an inherited MCP with the same name.</p>
    </fieldset>)}
    <p className="text-surface-500">{remote ? 'Finish saves this preset for new sessions on the remote Connector.' : 'Next keeps your changes in this draft. Test checks this preset with the harness; Finish saves it with the connection.'} Existing sessions keep their configuration.</p>
    {error && <p role="alert">{error}</p>}
  </section>;
}
