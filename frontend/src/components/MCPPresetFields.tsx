import type { MCPPreset } from '../api';
import { useEffect, useState } from 'react';
import { Pencil, Trash2 } from 'lucide-react';
import { AgentActionModal } from './AgentActionModal';
import { MCPCredentialsHelp } from './MCPCredentialsHelp';

const inputClass = 'block w-full min-w-0 rounded border p-2 bg-white dark:bg-surface-800';

function MappingFields({label, value, references, onChange}: {label: string; value: Record<string, string>; references: Record<string, string>; onChange: (value: Record<string, string>, references: Record<string, string>) => void}) {
  const [showValues, setShowValues] = useState(false);
  const entries = [...Object.entries(value).map(([key, item]) => ({key, item, source: 'value'})), ...Object.entries(references).map(([key, ref]) => ({key, item: ref.slice(ref.indexOf(':') + 1), source: ref.startsWith('vault:') ? 'vault' : 'provider'}))];
  const change = (rows: typeof entries) => onChange(Object.fromEntries(rows.filter(row => row.source === 'value').map(row => [row.key, row.item])), Object.fromEntries(rows.filter(row => row.source !== 'value').map(row => [row.key, `${row.source}:${row.item}`])));
  return <fieldset className="space-y-2 min-w-0"><legend className="font-medium">{label}</legend>
    {entries.map(({key, item, source}, index) => <div key={`${source}-${index}`} className="grid grid-cols-1 sm:grid-cols-[minmax(0,1fr)_9rem_minmax(0,1.5fr)_auto] gap-2">
      <input aria-label={`${label} name ${index + 1}`} className={inputClass} value={key} onChange={e => {
        if (entries.some((row, i) => i !== index && row.key.toLowerCase() === e.target.value.toLowerCase())) {
          e.target.setCustomValidity('This name is already in use.'); e.target.reportValidity(); return;
        }
        e.target.setCustomValidity('');
        change(entries.map((entry, i) => i === index ? {...entry, key: e.target.value} : entry));
      }} />
      <select aria-label={`${label} source ${index + 1}`} className={inputClass} value={source} onChange={e => change(entries.map((entry, i) => i === index ? {...entry, source: e.target.value, item: ''} : entry))}>
        <option value="value">Direct value</option><option value="provider">Host environment</option><option value="vault">Host vault</option>
      </select>
      <input aria-label={`${label} value ${index + 1}`} type={source === 'value' && !showValues ? 'password' : 'text'} autoComplete="off" spellCheck={false} className={inputClass} value={item} placeholder={source === 'provider' ? 'MY_MCP_TOKEN' : source === 'vault' ? 'stored-credential-name' : 'Value (saved in configuration)'}
        onChange={e => change(entries.map((entry, i) => i === index ? {...entry, item: e.target.value} : entry))} />
      <button type="button" className="btn btn-secondary" aria-label={`Remove ${label} ${index + 1}`}
        onClick={() => change(entries.filter((_, i) => i !== index))}>Remove</button>
    </div>)}
    <button type="button" className="btn btn-secondary" onClick={() => {
      let n = 1; while (entries.some(row => row.key === `VARIABLE_${n}`)) n++;
      change([...entries, {key: `VARIABLE_${n}`, item: '', source: 'value'}]);
    }}>Add {label.toLowerCase()}</button>
    {!!entries.length && <label className="ml-3 text-xs text-surface-500"><input type="checkbox" checked={showValues} onChange={e => setShowValues(e.target.checked)} /> Show direct values</label>}
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
    const headers = [...Object.keys(server.headers ?? {}), ...Object.keys(server.header_refs ?? {})].map(key => key.toLowerCase());
    if (new Set(headers).size !== headers.length) throw new Error(`${server.name}: each HTTP header needs a unique name.`);
  }
  return value;
}

export function MCPPresetFields({value, onChange, remote = false, standalone = false, onPendingChange}: {value: string; onChange: (text: string) => void; remote?: boolean; standalone?: boolean; onPendingChange?: (pending: boolean) => void}) {
  const servers = JSON.parse(value) as MCPPreset['servers'];
  const [editor, setEditor] = useState<{index: number | null; server: Record<string, unknown>} | null>(null);
  const [editorError, setEditorError] = useState('');
  const [notice, setNotice] = useState('');
  const [helpOpen, setHelpOpen] = useState(false);
  const applyHint = standalone ? 'Use Save MCP preset to apply this list.' : 'Finish the connection setup to apply this list.';
  useEffect(() => {onPendingChange?.(editor !== null);}, [editor !== null, onPendingChange]);
  useEffect(() => () => onPendingChange?.(false), [onPendingChange]);
  const update = (_index: number, changes: Record<string, unknown>) => {setEditor(current => current && {...current, server: {...current.server, ...changes}}); setEditorError('');};
  let error = '';
  try {parseMCPPreset(value);} catch (reason) {error = String(reason);}
  const add = (transport: 'stdio' | 'http') => {
    let index = servers.length + 1;
    while (servers.some(server => server.name === `server${index}`)) index++;
    setEditor({index: null, server: transport === 'stdio'
      ? {name: `server${index}`, enabled: true, transport, command: '', args: [], env: {}, env_refs: {}}
      : {name: `server${index}`, enabled: true, transport, url: '', header_refs: {}}});
    setEditorError(''); setNotice('');
  };
  const saveEditor = () => {
    if (!editor) return;
    const next = editor.index === null ? [...servers, editor.server] : servers.map((server, index) => index === editor.index ? editor.server : server);
    try {
      const text = JSON.stringify(next, null, 2); parseMCPPreset(text);
      onChange(text); setEditor(null); setEditorError('');
      setNotice(`MCP list updated in this draft. ${applyHint}`);
    } catch (reason) {setEditorError(reason instanceof Error ? reason.message : String(reason));}
  };
  return <section aria-label="Runtime MCP preset" className="space-y-3 border-t pt-3 min-w-0">
    <h5 className="font-semibold">MCP servers for this harness</h5>
    <p className="text-surface-500">Extra tools for new sessions. Servers with matching names override inherited MCPs.</p>
    <details className="text-surface-500"><summary className="cursor-pointer">Host paths and inheritance</summary><p className="mt-2 leading-relaxed">Commands run on the runtime host. Disabling a server also disables an inherited MCP with the same name. Nexus tools follow the agent permissions.</p></details>
    <div className="flex flex-wrap gap-2">
      <button type="button" className="btn btn-secondary" disabled={!!editor || servers.length >= 32} onClick={() => add('stdio')}>Add stdio MCP</button>
      <button type="button" className="btn btn-secondary" disabled={!!editor || servers.length >= 32} onClick={() => add('http')}>Add HTTP MCP</button>
    </div>
    {!servers.length && <p className="text-surface-500">No additional MCP servers configured.</p>}
    {!!servers.length && <ul aria-label="Added MCP servers" className="divide-y divide-surface-200 rounded-lg border border-surface-200 dark:divide-surface-700 dark:border-surface-700">
      {servers.map((server, index) => <li key={index} className="flex flex-wrap items-center gap-3 p-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2"><span className="font-medium break-all">{String(server.name)}</span>
            <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${server.transport === 'http' ? 'bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-300' : 'bg-violet-100 text-violet-700 dark:bg-violet-900/40 dark:text-violet-300'}`}>{server.transport === 'http' ? 'HTTP' : 'STDIO'}</span>
            {server.enabled === false && <span className="text-[10px] text-surface-500">Disabled</span>}
          </div>
          <p className="mt-1 truncate text-[11px] text-surface-500">{String(server.transport === 'http' ? server.url : server.command)}</p>
        </div>
        <button type="button" className="btn btn-secondary" disabled={!!editor} aria-label={`Edit MCP ${server.name}`} onClick={() => {setEditor({index, server: structuredClone(server)});setEditorError('');setNotice('');}}><Pencil size={13} /> Edit</button>
        <button type="button" className="btn btn-secondary" disabled={!!editor} aria-label={`Delete MCP ${server.name}`} onClick={() => {onChange(JSON.stringify(servers.filter((_, i) => i !== index), null, 2));setNotice(`MCP removed from this draft. ${applyHint}`);}}><Trash2 size={13} /> Delete</button>
      </li>)}
    </ul>}
    {editor && [editor.server].map((server, index) => <fieldset key="mcp-editor" aria-label="MCP editor" className="rounded-lg border p-3 space-y-3 min-w-0">
      <legend className="font-semibold px-1">{editor.index === null ? 'Add MCP server' : `Edit ${servers[editor.index]?.name}`}</legend>
      <div className="flex flex-wrap items-end gap-3">
        <label className="flex-1 min-w-0">Server name<input autoFocus className={inputClass} value={String(server.name ?? '')} maxLength={64}
          onChange={e => update(index, {name: e.target.value})} /></label>
        <label className="py-2"><input type="checkbox" checked={server.enabled !== false} onChange={e => update(index, {enabled: e.target.checked})} /> Enabled</label>
      </div>
      <label className="block">Connection type<select className={inputClass} value={String(server.transport)} onChange={e => {
        const replacement = e.target.value === 'stdio' ? {command: '', args: [], env: {}, env_refs: {}} : {url: '', header_refs: {}};
        setEditor({...editor, server: {name: server.name, enabled: server.enabled, transport: e.target.value, ...replacement}});setEditorError('');
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
        <details className="space-y-3" open={Object.keys(server.env as object ?? {}).length + Object.keys(server.env_refs as object ?? {}).length > 0 || undefined}>
          <summary className="cursor-pointer text-surface-500">Environment & credentials <span className="text-[10px]">Optional</span></summary>
          <MappingFields label="Environment variables" value={server.env as Record<string, string> ?? {}} references={server.env_refs as Record<string, string> ?? {}} onChange={(env, env_refs) => update(index, {env, env_refs})} />
        </details>
      </> : <>
        <label className="block">Server URL<input type="url" className={inputClass} value={String(server.url ?? '')} placeholder="https://example.com/mcp"
          onChange={e => update(index, {url: e.target.value})} /></label>
        <MappingFields label="HTTP headers" value={server.headers as Record<string, string> ?? {}} references={server.header_refs as Record<string, string> ?? {}} onChange={(headers, header_refs) => update(index, {headers, header_refs})} />
      </>}
      <p className="rounded bg-amber-50 p-2 text-xs text-amber-800 dark:bg-amber-950/30 dark:text-amber-200">Direct values are allowed and saved with the MCP configuration, including exports. For sensitive values, prefer an authorized reference to the runtime host environment or vault. <button type="button" className="underline font-medium" onClick={() => setHelpOpen(true)}>Help: storing MCP credentials</button></p>
      {editorError && <p role="alert">{editorError}</p>}
      <div className="flex justify-end gap-2 border-t border-surface-200 pt-3 dark:border-surface-700">
        <button type="button" className="btn btn-secondary" onClick={() => {setEditor(null);setEditorError('');}}>Cancel MCP editing</button>
        <button type="button" className="btn btn-primary" onClick={saveEditor}>{editor.index === null ? 'Add to list' : 'Save MCP changes'}</button>
      </div>
    </fieldset>)}
    {notice && <p role="status" className="text-xs text-emerald-700 dark:text-emerald-300">{notice}</p>}
    <p className="text-surface-500">{standalone ? 'Save MCP preset applies this list to new sessions.' : remote ? 'Finish saves this list for new sessions on the remote Connector.' : 'Add or save each MCP in this list, then continue with Next. Test checks the list with the harness; Finish saves it with the connection.'} Existing sessions keep their configuration.</p>
    {error && <p role="alert">{error}</p>}
    {helpOpen && <AgentActionModal title="Help · MCP credentials" onClose={() => setHelpOpen(false)} guardChanges={false}><MCPCredentialsHelp /></AgentActionModal>}
  </section>;
}
