import type { RuntimeRequest, RuntimeResolution, RuntimeSession, runtimeApi } from './runtimeApi';

type SessionApi = Pick<typeof runtimeApi, 'binding' | 'sessions' | 'session' | 'resolve' | 'submit'>;
export const sessionReleased = (session: RuntimeSession) => session.lifecycle_state === 'CLOSED' ||
  session.lifecycle_state === 'FAILED' && session.lease_state === 'CLOSED';

export async function connectionSessions(api: SessionApi, agentId: string, bindingIds: string[], signal?: AbortSignal) {
  const result: RuntimeSession[] = [];
  for (const id of bindingIds) {
    const binding = await api.binding(id);
    if (binding.agent_id !== agentId) throw new Error('The connection belongs to another agent. Reload its configuration.');
    let after = '';
    do {
      const page = await api.sessions(agentId, binding, after, signal);
      if (signal?.aborted) throw new DOMException('Cancelled', 'AbortError');
      if (page.sessions.some(s => s.scope.agent_id !== agentId || s.scope.binding_id !== id || s.scope.executor_id !== binding.executor_id))
        throw new Error('The returned sessions do not match this connection.');
      result.push(...page.sessions.filter(s => !sessionReleased(s)));
      if (!page.has_more) break;
      if (!page.next_after_session_id || page.next_after_session_id <= after)
        throw new Error('The session list changed. Refresh before continuing.');
      after = page.next_after_session_id;
    } while (true);
  }
  return result;
}

// Retain each immutable close request for safe retries after a lost HTTP response.
// Only the displayed snapshot is closed; newly arriving sessions need a new choice.
export class SessionClosures {
  private records = new Map<string, {request: RuntimeRequest; resolution?: RuntimeResolution}>();
  async close(api: SessionApi, session: RuntimeSession) {
    const scope = session.scope;
    const current = await api.session(scope.session_id, undefined, scope.executor_id);
    if (Object.keys(scope).some(key => current.scope[key as keyof typeof scope] !== scope[key as keyof typeof scope]))
      throw new Error('The session scope changed. Refresh before continuing.');
    if (sessionReleased(current)) return;
    const key = JSON.stringify(scope);
    let record = this.records.get(key);
    if (!record) {
      record = {request: {client_intent_id: 'setup_close_' + crypto.randomUUID().replaceAll('-', ''),
        agent_id: scope.agent_id, binding_id: scope.binding_id, workspace_binding_id: scope.workspace_binding_id,
        intent: 'runtime.close', session_id: scope.session_id}};
      this.records.set(key, record);
    }
    record.resolution ??= await api.resolve(record.request);
    const resolution = record.resolution;
    if (Object.keys(scope).some(key => resolution.scope[key as keyof typeof scope] !== scope[key as keyof typeof scope]))
      throw new Error('The close request does not match this session.');
    if (!resolution.can_submit) {
      // A blocked resolution submitted nothing. A later manual retry may review
      // readiness again; uncertain submissions always retain the same identity.
      this.records.delete(key);
      throw new Error('Cannot close this session yet: ' + resolution.blockers.join(', ') + '. Check its runtime status.');
    }
    const operation = await api.submit(resolution);
    if (operation.error) throw new Error(operation.error.message);
    return operation;
  }
}
