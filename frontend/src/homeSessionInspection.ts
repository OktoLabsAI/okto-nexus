import type {HomeSessionContext} from './homeTypes';
import type {RuntimeSession, runtimeApi} from './runtimeApi';

export function assertHomeSessionContext(session: RuntimeSession, expected: HomeSessionContext): void {
  if ((['server_id', 'executor_id', 'workspace_id', 'session_id', 'binding_id', 'workspace_binding_id', 'agent_id'] as const)
    .some(key => session.scope[key] !== expected[key]))
    throw new Error('The session no longer matches this exact context. No replacement was selected.');
}

/** Passive exact-session read; presence of IDs never authorizes a command. */
export async function readHomeSessionInspection(api: Pick<typeof runtimeApi, 'session'>, expected: HomeSessionContext, signal?: AbortSignal) {
  const session = await api.session(expected.session_id, signal, expected.executor_id);
  if (signal?.aborted) throw new DOMException('Read cancelled.', 'AbortError');
  assertHomeSessionContext(session, expected);
  return session;
}
