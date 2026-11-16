import type {runtimeApi, RuntimeScope, RuntimeSession} from '../../runtimeApi';
import type {HomeTarget} from '../../homeTypes';
type Reads = Pick<typeof runtimeApi, 'session' | 'binding'>;
export function sameRuntimeScope(left: RuntimeScope, right: RuntimeScope): boolean {
  return (['server_id', 'agent_id', 'executor_id', 'binding_id', 'workspace_id', 'workspace_binding_id', 'session_id'] as const)
    .every(key => left[key] === right[key]);
}
export function assertContinuableSession(session: RuntimeSession, scope: RuntimeScope): void {
  if (!sameRuntimeScope(session.scope, scope) || !session.control_available || session.durable_release_pending ||
      ['CLOSED', 'FAILED', 'CLOSING', 'DRAINING'].includes(session.lifecycle_state) || session.lease_state === 'CLOSED')
    throw new Error('This exact session cannot accept a continuation. Choose a new context explicitly; no replacement session was selected.');
}
export async function revalidateContinuation(client: Pick<Reads, 'session'>, scope: RuntimeScope): Promise<void> {
  const current = await client.session(scope.session_id, undefined, scope.executor_id);
  assertContinuableSession(current, scope);
}
export async function readContinuationContext(client: Reads, target: HomeTarget, agentId: string | undefined, signal?: AbortSignal) {
  if ((target.kind !== 'execution' && target.kind !== 'result' && target.kind !== 'session') || !agentId || !target.workspace_id)
    throw new Error('The exact session and recipient are required.');
  const session = await client.session(target.session_id, signal, target.executor_id);
  if (session.scope.server_id !== target.server_id || session.scope.executor_id !== target.executor_id ||
      session.scope.session_id !== target.session_id || session.scope.workspace_id !== target.workspace_id || session.scope.agent_id !== agentId)
    throw new Error('The session no longer matches this exact result.');
  assertContinuableSession(session, session.scope);
  const binding = await client.binding(session.scope.binding_id);
  if (signal?.aborted) throw new DOMException('Read cancelled.', 'AbortError');
  if (binding.binding_id !== session.scope.binding_id || binding.agent_id !== session.scope.agent_id ||
      binding.executor_id !== session.scope.executor_id || binding.workspace_id !== session.scope.workspace_id ||
      binding.workspace_binding_id !== session.scope.workspace_binding_id)
    throw new Error('The binding no longer matches this exact session.');
  return {session, binding};
}

/** Remove only Home's reviewed recovery messages when operator authority ends. */
export function clearHomeContinuationRequests(storage: Pick<Storage, 'length' | 'key' | 'removeItem'>): void {
  const prefix = 'okto-nexus:r4-runtime:';
  const remove: string[] = [];
  for (let i=0; i<storage.length; i++) {
    const key = storage.key(i);if (!key?.startsWith(prefix)) continue;
    try {
      const scope = JSON.parse(key.slice(prefix.length));
      if (Array.isArray(scope) && scope.length === 7 && scope[4] === 'home-continuation') remove.push(key);
    } catch { /* Unrelated or malformed records are not rewritten. */ }
  }
  remove.forEach(key => storage.removeItem(key));
}
