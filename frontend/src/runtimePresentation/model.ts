import type { RuntimeEventPage } from '../runtimeApi';

export type SessionEvent = RuntimeEventPage['events'][number];
export type Fields = {label: string; value: string}[];
export type ActionKind = 'assistant' | 'user' | 'tool' | 'thinking' | 'status' | 'error' | 'approval';
export interface TerminalAction {
  id: string; kind: ActionKind; title: string; text?: string; fields?: Fields; output?: string;
  status?: string; time?: string; sequence?: number;
}
export interface ActionUpdate extends Omit<TerminalAction, 'time' | 'sequence'> {
  append?: boolean; appendOutput?: boolean;
}
export interface AdapterContext {
  turn: string; message: string; serial: number; blocks: Map<number, string>;
  partialInputs: Map<string, string>; messageFinished: boolean;
}
export interface HarnessAdapter {
  id: string; matches: (event: SessionEvent) => boolean;
  adapt: (event: SessionEvent, context: AdapterContext) => ActionUpdate[] | null;
}
export const object = (value: unknown): Record<string, unknown> =>
  value !== null && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};
export const string = (value: unknown): string => typeof value === 'string' ? value : '';
// Native text placeholders are transport metadata, never display content.
// Do not remove [REDACTED]: that marker represents an actual protected secret.
export function withoutNativeText(value: unknown): unknown {
  if (value === '[NATIVE_TEXT_REDACTED]') return undefined;
  if (Array.isArray(value)) return value.map(withoutNativeText).filter(v=>v!==undefined);
  if (value && typeof value === 'object') return Object.fromEntries(Object.entries(object(value))
    .map(([key,item])=>[key,withoutNativeText(item)]).filter(([,item])=>item!==undefined));
  return value;
}
export const label = (value: string) => value.replace(/([a-z])([A-Z])/g, '$1 $2').replace(/[_/.:]+/g, ' ').replace(/^./, v => v.toUpperCase());
export function decoded(value: unknown): unknown {
  if (typeof value !== 'string') return value;
  try { return JSON.parse(value); } catch { return value; }
}
// Bound arbitrary tool results and never render objects with JSON.stringify.
// Escape sequences are inert text; React owns escaping, including HTML in output.
export function clean(value: string): string {
  return value.replace(/\x1b\[[0-?]*[ -/]*[@-~]/g, '').replace(/\x1b\][^\x07]*(?:\x07|\x1b\\)/g, '')
    .replace(/[\x00-\x08\x0b-\x1f\x7f]/g, '').slice(0, 32000);
}
export function fields(value: unknown, prefix = '', depth = 0): Fields {
  if (depth > 6) return [{label: prefix || 'Value', value: 'Additional nested content omitted'}];
  if (typeof value === 'string') {
    const parsed = decoded(value);
    if (typeof parsed !== 'string') return fields(parsed, prefix, depth + 1);
    return value.trim() ? [{label: prefix || 'Value', value: clean(value)}] : [];
  }
  if (typeof value === 'number' || typeof value === 'boolean') return [{label: prefix || 'Value', value: String(value)}];
  if (Array.isArray(value)) return value.slice(0, 50).flatMap((v, i) => fields(v, `${prefix} ${i + 1}`.trim(), depth + 1)).slice(0, 100);
  return Object.entries(object(value)).slice(0, 50).flatMap(([k,v]) => {
    const name = prefix ? `${prefix} · ${label(k)}` : label(k);
    return /^(authorization|api[_-]?key|access[_-]?token|password|secret|env|headers|http_headers)$/i.test(k)
      ? [{label: name, value: '[Protected value]'}] : fields(v, name, depth + 1);
  }).slice(0, 100);
}
export function content(value: unknown): string {
  if (typeof value === 'string') return fields(value).map(f => f.label === 'Value' ? f.value : `${f.label}: ${f.value}`).join('\n');
  if (Array.isArray(value)) return value.map(v => {
    const b = object(v);
    if (b.type === 'text' || b.type === 'input_text' || b.type === 'output_text') return content(b.text);
    if (b.type === 'image' || b.type === 'image_url') return '[Image]';
    return content(v);
  }).filter(Boolean).join('\n');
  const obj = object(value);
  if ('content' in obj) return content(obj.content);
  return fields(value).map(f => `${f.label}: ${f.value}`).join('\n');
}
export function tool(id: string, name: unknown, input: unknown, output?: unknown, status?: string): ActionUpdate {
  return {id, kind: 'tool', title: string(name) || 'Tool', fields: fields(decoded(input)), output: content(output), status};
}
