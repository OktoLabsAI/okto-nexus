import { MCPPresetFields, parseMCPPreset } from './MCPPresetFields';
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
  return <section aria-label="Runtime MCP preset" className="space-y-3 border-t pt-3 min-w-0">
    <fieldset disabled={busy || !saved}><MCPPresetFields value={text} onChange={value => setText(value)} /></fieldset>
    <button className="btn btn-secondary" disabled={busy || !saved || !dirty} onClick={async () => {
      if (!saved) return;
      setError(''); setNotice('');
      try {const servers = parseMCPPreset(text); setBusy(true);
        const p = await api.saveMcpPreset(endpoint, {expected_revision: saved.revision, servers});
        setSaved(p); setText(format(p.servers)); setNotice('MCP preset saved. New sessions use this configuration.');}
      catch (e) {setError(String(e));} finally {setBusy(false);}
    }}>Save MCP preset</button>
    <button className="btn btn-secondary ml-2" disabled={busy} onClick={() => setReload(n => n + 1)}>Reload MCP preset</button>
    {error && <p role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}
  </section>;
}
