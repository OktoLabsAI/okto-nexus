import type { MCPPreset } from '../api';

export function parseMCPPreset(text: string): MCPPreset['servers'] {
  if (new TextEncoder().encode(text).length > 32768) throw new Error('MCP preset must be 32 KiB or smaller.');
  const value = JSON.parse(text);
  if (!Array.isArray(value) || value.some(server => !server || typeof server !== 'object' || Array.isArray(server)))
    throw new Error('Enter a JSON array of MCP servers.');
  return value;
}

export function MCPPresetFields({value, onChange, remote = false}: {value: string; onChange: (text: string) => void; remote?: boolean}) {
  let error = '';
  try {parseMCPPreset(value);} catch (reason) {error = String(reason);}
  const add = (transport: 'stdio' | 'http') => {
    const servers = parseMCPPreset(value);
    let index = servers.length + 1;
    while (servers.some(server => server.name === `server${index}`)) index++;
    servers.push(transport === 'stdio'
      ? {name: `server${index}`, enabled: true, transport, command: '', args: [], env: {}, env_refs: {}}
      : {name: `server${index}`, enabled: true, transport, url: '', header_refs: {}});
    onChange(JSON.stringify(servers, null, 2));
  };
  return <section aria-label="Runtime MCP preset" className="space-y-3 border-t pt-3 min-w-0">
    <h5 className="font-semibold">MCP servers for this harness</h5>
    <p className="text-surface-500">Add the MCPs this agent needs in new runtime sessions. These work together with the harness global MCP inheritance setting. A matching name replaces an inherited server; enabled: false disables it.</p>
    <p className="text-surface-500">Commands and paths run on the runtime host. Use env_refs or header_refs for credentials already authorized on that host. Nexus tools follow the agent permissions.</p>
    <div className="flex flex-wrap gap-2">
      <button type="button" className="btn btn-secondary" disabled={!!error} onClick={() => add('stdio')}>Add stdio MCP</button>
      <button type="button" className="btn btn-secondary" disabled={!!error} onClick={() => add('http')}>Add HTTP MCP</button>
    </div>
    <label className="block">MCP preset JSON
      <textarea aria-label="MCP preset JSON" spellCheck={false} rows={10} value={value}
        className="block w-full min-w-0 max-w-full rounded border p-2 font-mono text-xs bg-white dark:bg-surface-800"
        onChange={event => onChange(event.target.value)} />
    </label>
    <p className="text-surface-500">{remote ? 'Finish saves this preset for new sessions on the remote Connector.' : 'Next keeps your changes in this draft. Test checks this preset with the harness; Finish saves it with the connection.'} Existing sessions keep their configuration.</p>
    {error && <p role="alert">{error}</p>}
  </section>;
}
