import type {InteractionScope, SessionInputReceipt, SessionSteerAvailability} from './runtimeApi';
import {assertInteractionScope, interactionKey} from './sessionConversation';

export type SteerSource = {kind: 'draft'; text: string; catalogRevision?: string} | {kind: 'queue'; inputId: string};
export type SteerReference = {kind: 'draft'; intent: string} | {kind: 'queue'; inputId: string};

const prefix = 'okto-nexus:session-steer:';

export function steerStorageKey(scope: InteractionScope) {
  return prefix + interactionKey(scope);
}

export function readSteerReference(storage: Storage, key: string): SteerReference | null {
  try {
    const value = JSON.parse(storage.getItem(key) ?? 'null');
    if (value?.kind === 'draft' && typeof value.intent === 'string' &&
        /^ui_steer_[0-9a-f-]{36}$/.test(value.intent)) return {kind: 'draft', intent: value.intent};
    if (value?.kind === 'queue' && typeof value.inputId === 'string' &&
        value.inputId.length > 0 && value.inputId.length <= 160) return {kind: 'queue', inputId: value.inputId};
  } catch {
    return null;
  }
  return null;
}

export function clearSteerReferences(storage: Storage) {
  for (let index = storage.length - 1; index >= 0; index -= 1) {
    const key = storage.key(index);
    if (key?.startsWith(prefix)) storage.removeItem(key);
  }
}

export function assertSteerPreview(value: SessionSteerAvailability, scope: InteractionScope, source: SteerSource) {
  assertInteractionScope({...value.scope, session_owner_generation: value.session_owner_generation}, scope);
  const control = value.control;
  if (!control) return;
  if (control.effect !== 'same_turn' || control.target?.kind !== 'native_turn' || !control.target.turn_id ||
      !control.capability_revision || !control.effect_revision || !Number.isSafeInteger(control.queue_revision) ||
      control.queue_revision < 0) throw new Error('The exact reorientation could not be verified.');
  if (source.kind === 'queue' && (value.queued_input?.input_id !== source.inputId ||
      !Number.isSafeInteger(value.queued_input.input_revision) || value.queued_input.input_revision < 0)) {
    throw new Error('The queued message could not be verified.');
  }
}

export function steerReceiptOutcome(receipt: SessionInputReceipt, scope: InteractionScope, reference: SteerReference) {
  assertInteractionScope({...receipt.scope, session_owner_generation: receipt.session_owner_generation}, scope);
  if (reference.kind === 'queue' && receipt.input_id !== reference.inputId) throw new Error('Invalid reorientation receipt.');
  if (receipt.reorientation !== true) {
    if (reference.kind === 'draft' || receipt.reorientation !== false) throw new Error('Invalid reorientation receipt.');
    return ['QUEUED', 'PAUSED'].includes(receipt.status) ? 'uncertain' : 'original-changed';
  }
  if (!receipt.operation_id) throw new Error('Invalid reorientation receipt.');
  if (receipt.status === 'ACCEPTED_NATIVE') return 'accepted';
  if (receipt.steer_submitted === true && receipt.status === 'DISPATCHING') return 'submitted';
  if (receipt.status === 'REFUSED_BEFORE_SEND' && !receipt.possible_effect) return 'refused';
  if (receipt.status === 'DISPATCHING' && !receipt.possible_effect) return 'dispatching';
  return 'uncertain';
}
