import type { HomeResolvedTarget, HomeTarget } from './homeTypes';
import type { AttentionTarget } from './attentionNavigation';

const fields: Record<HomeTarget['kind'], readonly string[]> = {
  handoff: ['handoff_id'], execution: ['executor_id', 'session_id', 'operation_id'],
  result: ['executor_id', 'session_id', 'operation_id'], message: ['message_id'],
  approval: ['approval_id'], external_observation: ['source_id', 'observed_instance_id', 'generation'],
  session: ['executor_id', 'session_id'], connection: ['executor_id', 'binding_id', 'agent_id'],
};
const identity = (value: unknown): value is string => typeof value === 'string' && value.length > 0 &&
  value.length <= 256 && !/[\u0000-\u001f]/.test(value);

/** IDs are opaque. Colons, slashes and Unicode have no routing semantics. */
export function parseHomeTarget(value: unknown): HomeTarget | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  const v = value as Record<string, unknown>;
  if (typeof v.kind !== 'string' || !Object.hasOwn(fields, v.kind) || !identity(v.server_id) ||
      !(v.workspace_id === null || identity(v.workspace_id))) return null;
  const kind = v.kind as HomeTarget['kind'];
  if ((kind === 'session' || kind === 'connection') && !identity(v.workspace_id)) return null;
  const required = fields[kind];
  const allowed = ['kind', 'server_id', 'workspace_id', ...required];
  if (Object.keys(v).some(key => !allowed.includes(key))) return null;
  for (const key of required) {
    if (key === 'generation') {
      if (!Number.isSafeInteger(v[key]) || (v[key] as number) < 1) return null;
    } else if (!identity(v[key])) return null;
  }
  return v as unknown as HomeTarget;
}
export function encodeHomeTarget(target: HomeTarget): string {
  const valid = parseHomeTarget(target);
  if (!valid) throw new Error('Invalid Home target.');
  return JSON.stringify(Object.fromEntries(Object.entries(valid).sort(([a], [b]) => a.localeCompare(b))));
}
export function decodeHomeTarget(encoded: string): HomeTarget | null {
  if (encoded.length > 10000) return null;
  try { return parseHomeTarget(JSON.parse(encoded)); } catch { return null; }
}
export function homeTargetSearch(target: HomeTarget): string {
  return new URLSearchParams({ home_target: encodeHomeTarget(target) }).toString();
}
export async function resolveHomeTarget(
  api: { target(target: HomeTarget, workspace: string | null, signal?: AbortSignal): Promise<HomeResolvedTarget> },
  target: HomeTarget, expected: { server_id: string; workspace_id: string | null }, signal?: AbortSignal,
): Promise<HomeResolvedTarget> {
  if (!parseHomeTarget(target) || target.server_id !== expected.server_id ||
      (expected.workspace_id !== null && target.workspace_id !== expected.workspace_id))
    throw new Error('Home target is outside the current scope.');
  const value = await api.target(target, expected.workspace_id, signal);
  if (value.version !== 1 || !parseHomeTarget(value.target) ||
      encodeHomeTarget(value.target) !== encodeHomeTarget(target)) throw new Error('Home target changed.');
  if (target.kind === 'session' || target.kind === 'connection') {
    const context = target.kind === 'session' ? value.session_context : value.connection_context;
    if (!context || context.server_id !== target.server_id || context.executor_id !== target.executor_id ||
        context.workspace_id !== target.workspace_id || !identity(context.binding_id) || !identity(context.workspace_binding_id) ||
        !identity(context.agent_id) || context.agent_id !== value.agent_id ||
        (target.kind === 'session' && (!value.session_context || value.session_context.session_id !== target.session_id)) ||
        (target.kind === 'connection' && (context.binding_id !== target.binding_id || context.agent_id !== target.agent_id)))
      throw new Error('Home target context changed.');
  }
  return value;
}

/** Reuse canonical inspectors after the server has resolved the exact target. */
export function homeInspectionTarget(resolved: HomeResolvedTarget): AttentionTarget {
  const target = parseHomeTarget(resolved.target);
  const unavailable: AttentionTarget = { kind: 'unavailable', reason: 'The exact canonical target is unavailable.' };
  if (!resolved.available || !target || !resolved.source_revision) return unavailable;
  switch (target.kind) {
    case 'session': {
      const c=resolved.session_context;
      return c&&c.server_id===target.server_id&&c.executor_id===target.executor_id&&c.workspace_id===target.workspace_id&&
        c.session_id===target.session_id&&identity(c.binding_id)&&identity(c.workspace_binding_id)&&identity(c.agent_id)&&c.agent_id===resolved.agent_id
        ? {kind:'session',context:c} : unavailable;
    }
    case 'connection': {
      const c=resolved.connection_context;
      return c&&c.server_id===target.server_id&&c.executor_id===target.executor_id&&c.workspace_id===target.workspace_id&&
        c.binding_id===target.binding_id&&c.agent_id===target.agent_id&&identity(c.workspace_binding_id)&&c.agent_id===resolved.agent_id
        ? {kind:'connection',context:c} : unavailable;
    }
    case 'handoff': return target.workspace_id ? { kind: 'handoff', id: target.handoff_id, workspace: target.workspace_id, verify: false } : unavailable;
    case 'message': return { kind: 'message', id: target.message_id, workspace: target.workspace_id };
    case 'approval': return { kind: 'approval', id: target.approval_id, workspace: target.workspace_id, decide: false };
    case 'result':
    case 'execution': return identity(resolved.agent_id) ? { kind: 'execution', agent: resolved.agent_id,
      executor: target.executor_id, operation: target.operation_id, session: target.session_id, workspace: target.workspace_id } : unavailable;
    case 'external_observation': return identity(resolved.agent_id) && target.workspace_id ? { kind: 'external_observation',
      id: target.observed_instance_id, source: target.source_id, generation: target.generation,
      workspace: target.workspace_id, agent: resolved.agent_id } : unavailable;
  }
}
