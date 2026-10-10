import type { RuntimeEventPage, RuntimeScope } from './runtimeApi';

export function validateEventPage(page: RuntimeEventPage, scope: RuntimeScope, after: number, epoch: string | null) {
  if (['server_id','executor_id','session_id','agent_id','binding_id','workspace_id','workspace_binding_id'].some(
      key => page.scope[key as keyof RuntimeScope] !== scope[key as keyof RuntimeScope]) ||
      epoch !== null && page.stream_epoch !== epoch || page.count !== page.events.length || page.events.length > 100 ||
      page.events.some((event, index) => event.server_id !== scope.server_id || event.executor_id !== scope.executor_id ||
        event.session_id !== scope.session_id || event.stream_epoch !== page.stream_epoch || event.sequence !== after + index + 1) ||
      page.next_after_sequence !== after + page.events.length || page.has_more && !page.events.length)
    throw new Error('The event page does not match this session and cursor.');
}

export function appendTail(previous: RuntimeEventPage['events'], incoming: RuntimeEventPage['events']) {
  return [...previous, ...incoming.filter(event => event.sequence > (previous.at(-1)?.sequence ?? 0))].slice(-200);
}
