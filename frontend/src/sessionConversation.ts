import type {ConversationUpdate, InteractionScope, SessionConversationPage, SessionConversationPosition, SessionInputReceipt} from './runtimeApi';
import {sameRuntimeScope} from './components/home/continuation';

export function interactionKey(scope: InteractionScope) {
  return JSON.stringify([scope.server_id, scope.executor_id, scope.binding_id, scope.workspace_id,
    scope.workspace_binding_id, scope.agent_id, scope.session_id, scope.session_owner_generation]);
}

const inputIntentPrefix = 'okto-nexus:session-input:';

export function inputIntentStorageKey(scope: InteractionScope) {
  return inputIntentPrefix + interactionKey(scope);
}

export function readInputIntent(storage: Storage, key: string) {
  const intent = storage.getItem(key);
  return intent && /^ui_[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/.test(intent) ? intent : null;
}

export function clearInputIntents(storage: Storage) {
  for (let index = storage.length - 1; index >= 0; index -= 1) {
    const key = storage.key(index);
    if (key?.startsWith(inputIntentPrefix)) storage.removeItem(key);
  }
}

export function assertInteractionScope(actual: InteractionScope, expected: InteractionScope) {
  if (!sameRuntimeScope(actual, expected) || actual.session_owner_generation !== expected.session_owner_generation) {
    throw new Error('The response belongs to a different session.');
  }
}

export function assertConversationPage(page: SessionConversationPage, scope: InteractionScope, after: number, epoch: string | null) {
  assertInteractionScope(page.scope, scope);
  if ((epoch !== null && page.stream_epoch !== epoch) ||
      !Number.isSafeInteger(page.next_after_sequence) || page.next_after_sequence < after ||
      !Number.isSafeInteger(page.committed_contiguous) || page.committed_contiguous < page.next_after_sequence ||
      (page.has_more && page.next_after_sequence === after) ||
      page.updates.length > 400 || page.updates.some(update => !Number.isSafeInteger(update.sequence) ||
        update.sequence <= after || update.sequence > page.next_after_sequence ||
        !['append', 'replace'].includes(update.change) || !['user', 'assistant'].includes(update.role) ||
        (update.origin?.kind === 'subagent' && (update.role !== 'assistant' ||
          typeof update.origin.session_id !== 'string' || !update.origin.session_id ||
          typeof update.origin.parent_tool_use_id !== 'string' || !update.origin.parent_tool_use_id)) ||
        !(update.text === null || typeof update.text === 'string'))) {
    throw new Error('The conversation page did not match its cursor.');
  }
}

export function assertConversationPosition(position: SessionConversationPosition, scope: InteractionScope) {
  assertInteractionScope(position.scope, scope);
  if (position.version !== 1 || !Number.isSafeInteger(position.committed_contiguous) || position.committed_contiguous < 0 ||
      typeof position.gap_pending !== 'boolean' ||
      (position.stream_epoch === null ? position.committed_contiguous !== 0 || position.gap_pending
        : typeof position.stream_epoch !== 'string' || !position.stream_epoch || position.stream_epoch.length > 160)) {
    throw new Error('The conversation position is invalid.');
  }
}

export interface ConversationMessage {
  role: ConversationUpdate['role'];
  text: string;
  truncated: boolean;
  subagent?: true;
}

export function applyConversationUpdates(previous: ReadonlyMap<string, ConversationMessage>, updates: ConversationUpdate[]) {
  const next = new Map(previous);
  const seen = new Set<string>();
  for (const update of updates) {
    if (seen.has(update.update_id)) continue;
    seen.add(update.update_id);
    const prior = update.change === 'append' ? next.get(update.message_id) : undefined;
    // After an omitted suffix, a later fragment would splice unrelated text
    // into the visible prefix. A complete snapshot can restore the message.
    if (prior?.truncated) continue;
    const text = (prior?.text ?? '') + (update.text ?? '');
    const limit = 16384;
    next.set(update.message_id, {role: update.role, text: text.slice(0, limit),
      truncated: update.text_truncated || !!prior?.truncated || text.length > limit,
      ...(update.origin?.kind === 'subagent' ? {subagent: true} : {})});
  }
  return next;
}

export const receiptLabel: Record<SessionInputReceipt['status'], string> = {
  QUEUED: 'Queued for the next turn',
  DISPATCHING: 'Sending to the harness',
  ACCEPTED_NATIVE: 'Accepted by the harness',
  REFUSED_BEFORE_SEND: 'Refused before sending',
  DELIVERY_UNKNOWN: 'Delivery could not be confirmed',
  BLOCKED_AUTH: 'Blocked by authorization',
  BLOCKED_SESSION: 'Blocked because the session is unavailable',
  PAUSED: 'Queue paused',
  EXPIRED: 'Queue entry expired',
  CANCELLED: 'Removed from the queue',
};
