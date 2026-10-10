import { useEffect, useState } from 'react';
import { api, type MCPPreset } from '../api';

export function RuntimeMCPPreset({endpoint, onPendingChange}: {endpoint: string; onPendingChange?: (pending: boolean) => void}) {
  const [saved, setSaved] = useState<MCPPreset | null>(null);
  const [text, setText] = useState('[]');
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [reload, setReload] = useState(0);
  const format = (servers: MCPPreset['servers']) => JSON.stringify(servers, null, 2);
  useEffect(() => {
    let active = true;
    setBusy(true); setSaved(null); setError(''); setNotice('');
    api.mcpPreset(endpoint).then(p => {if (active) {setSaved(p); setText(format(p.servers));}})
      .catch(e => {if (active) setError(String(e));}).finally(() => {if (active) setBusy(false);});
    return () => {active = false;};
  }, [endpoint, reload]);
  const dirty = !saved || text !== format(saved.servers);
  useEffect(() => {onPendingChange?.(busy || dirty);}, [busy, dirty, onPendingChange]);
  const parse = () => {
    if (new TextEncoder().encode(text).length > 32768) throw new Error('MCP preset must be 32 KiB or smaller.');
    const result = JSON.parse(text);
    if (!Array.isArray(result) || result.some(v => !v || typeof v !== 'object' || Array.isArray(v))) throw new Error('Enter a JSON array of MCP servers.');
    return result as MCPPreset['servers'];
  };
  const add = (transport: 'stdio' | 'http') => {
    try {const servers = parse(); servers.push(transport === 'stdio'
      ? {name: `server${servers.length + 1}`, enabled: true, transport, command: '', args: [], env: {}, env_refs: {}}
      : {name: `server${servers.length + 1}`, enabled: true, transport, url: '', header_refs: {}});
      setText(format(servers)); setError(''); setNotice('');}
    catch (e) {setError(String(e));}
  };
  return <section aria-label="Runtime MCP preset" className="space-y-3 border-t pt-3 min-w-0">
    <h5 className="font-semibold">MCP preset for this harness</h5>
    <p className="text-xs text-surface-500">Applied to new runtime sessions. When global harness MCPs are enabled, a preset replaces servers with the same name; enabled: false removes that server. Nexus tools remain available according to agent permissions.</p>
    <p className="text-xs text-surface-500">Commands and paths run on the runtime host. Use env_refs or header_refs for credentials, with references already authorized on that host, such as vault:docs-token. Do not paste credentials into this editor.</p>
    <div className="flex flex-wrap gap-2"><button className="btn btn-secondary" disabled={busy || !saved} onClick={() => add('stdio')}>Add stdio MCP</button>
      <button className="btn btn-secondary" disabled={busy || !saved} onClick={() => add('http')}>Add HTTP MCP</button></div>
    <textarea aria-label="MCP preset JSON" spellCheck={false} rows={12} disabled={busy || !saved} value={text}
      className="block w-full min-w-0 max-w-full rounded border p-2 font-mono text-xs bg-white dark:bg-surface-800"
      onChange={e => {setText(e.target.value); setNotice('');}} />
    <button className="btn btn-secondary" disabled={busy || !saved || !dirty} onClick={async () => {
      if (!saved) return;
      setError(''); setNotice('');
      try {const servers = parse(); setBusy(true);
        const p = await api.saveMcpPreset(endpoint, {expected_revision: saved.revision, servers});
        setSaved(p); setText(format(p.servers)); setNotice('MCP preset saved. New sessions use this configuration.');}
      catch (e) {setError(String(e));} finally {setBusy(false);}
    }}>Save MCP preset</button>
    <button className="btn btn-secondary ml-2" disabled={busy} onClick={() => setReload(n => n + 1)}>Reload MCP preset</button>
    {error && <p role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}
  </section>;
}
