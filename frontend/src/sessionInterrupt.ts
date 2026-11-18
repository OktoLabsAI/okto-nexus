import type {InteractionScope, SessionInterruptReceipt} from './runtimeApi';
import {interactionKey} from './sessionConversation';

const prefix = 'okto-nexus:session-interrupt:';

export function interruptStorageKey(scope: InteractionScope) {
  return prefix + interactionKey(scope);
}

export function clearInterruptIntents(storage: Storage) {
  for (let index = storage.length - 1; index >= 0; index -= 1) {
    const key = storage.key(index);
    if (key?.startsWith(prefix)) storage.removeItem(key);
  }
}

export function interruptStatus(receipt: SessionInterruptReceipt) {
  const {target_status} = receipt.interrupt;
  if (target_status === 'interrupted') return 'Turn interrupted.';
  if (target_status === 'finished') return 'The selected turn ended.';
  if (receipt.error && !receipt.possible_effect) {
    return target_status === 'running' ? 'Interrupt refused. The selected turn is still running.'
      : 'Interrupt refused. The turn’s state is unconfirmed.';
  }
  if (receipt.executor_stage === 'OUTCOME_UNKNOWN' || receipt.admission_state === 'RECONCILING') {
    return 'The interrupt outcome is unconfirmed.';
  }
  if (receipt.executor_stage === 'SUBMITTED' || receipt.executor_stage === 'SUCCEEDED') {
    return 'Interrupt delivered. Waiting to confirm that the turn stopped.';
  }
  return 'Interrupt requested. Waiting for the harness.';
}

export function canDismissInterrupt(receipt: SessionInterruptReceipt | null) {
  return !!receipt && (receipt.interrupt.target_status === 'interrupted' || receipt.interrupt.target_status === 'finished'
    || (!!receipt.error && !receipt.possible_effect));
}
