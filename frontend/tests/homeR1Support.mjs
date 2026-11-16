import { readFile } from 'node:fs/promises';
import ts from 'typescript';
export async function moduleURL(name, replacements = {}) {
  const source = await readFile(new URL(`../src/${name}`, import.meta.url), 'utf8');
  let code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText;
  for (const [from, to] of Object.entries(replacements)) code = code.replaceAll(`'${from}'`, `'${to}'`).replaceAll(`"${from}"`, `"${to}"`);
  return `data:text/javascript;base64,${Buffer.from(code).toString('base64')}`;
}
export const flush = async () => { for (let i = 0; i < 30; i++) await Promise.resolve(); };
export function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
export class Clock {
  now = 0; sequence = 0; timers = new Map();
  set = (callback, delay) => { const id = ++this.sequence; this.timers.set(id, { at: this.now + delay, callback }); return id; };
  clear = id => this.timers.delete(id);
  async advance(ms = 0) {
    const end = this.now + ms;
    let count = 0;
    while (true) {
      const next = [...this.timers].filter(([, t]) => t.at <= end).sort((a, b) => a[1].at - b[1].at)[0];
      if (!next) break;
      if (++count > 500) throw new Error('Unbounded timer loop');
      this.now = next[1].at; this.timers.delete(next[0]); next[1].callback(); await flush();
    }
    this.now = end; await flush();
  }
}
export const section = (items = [], patch = {}) => ({ status: 'ready', as_of: '2030-01-01T00:00:00Z',
  next_refresh_at: null, items, total: items.length, total_is_exact: true, has_more: false, next_cursor: null, revision: 'r1', ...patch });
export const overview = (patch = {}) => ({ version: 1, scope: { workspace_id: 'ws' }, server_id: 'server',
  generated_at: '2030-01-01T00:00:00Z', snapshot_id: 'snapshot1', event_cursor: 5, event_low_watermark: 1,
  summary: {}, work: section([{ id: 'work1' }]), attention: section(), server_attention: section(), results: section(), agents: section(), external_activity: section(), ...patch });
export const page = (items, patch = {}) => ({ ...section(items), version: 1, scope: { workspace_id: 'ws' },
  server_id: 'server', generated_at: '2030-01-01T00:00:00Z', snapshot_id: 'snapshot1', ...patch });
