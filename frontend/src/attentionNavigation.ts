import type {AttentionAction, AttentionOccurrence} from './attentionTypes';
import type {api as canonicalApi, ApprovalDetail} from './api';

export type AttentionTarget =
  | {kind: 'approval'; id: string; workspace: string | null; decide: boolean}
  | {kind: 'handoff'; id: string; workspace: string; verify: boolean}
  | {kind: 'message'; id: string; workspace: string | null}
  | {kind: 'execution'; agent: string; executor: string; operation: string; session: string | null; workspace: string | null}
  | {kind: 'delivery'; operation: string; workspace: string; agent: string | null}
  | {kind: 'maintenance'; id: string; result: string | null; workspace: string | null; agent: string | null}
  | {kind: 'unavailable'; reason: string};

const unavailable = (reason: string): AttentionTarget => ({kind: 'unavailable', reason});
const reference = (value: string | null): value is string => typeof value === 'string' && value.length > 0;

/** Resolve explicit canonical references only. This function never executes a command. */
export function attentionTarget(item: AttentionOccurrence, action: AttentionAction): AttentionTarget {
  if (!item.allowed_actions.includes(action)) return unavailable('This action is no longer offered. Refresh attention.');
  const approval = ['approval', 'execution_native_request'].includes(item.source_type);
  const handoff = ['handoff', 'handoff_result'].includes(item.source_type);
  if (['inspect_approval', 'respond_native', 'decide_native', 'decide_approval'].includes(action)) {
    return approval && reference(item.source_id) ? {kind: 'approval', id: item.source_id,
      workspace: item.workspace_id, decide: action !== 'inspect_approval'} : unavailable('The canonical approval reference is unavailable.');
  }
  if (['inspect_handoff', 'verify_handoff'].includes(action)) {
    return handoff && reference(item.source_id) && reference(item.workspace_id)
      ? {kind: 'handoff', id: item.source_id, workspace: item.workspace_id, verify: action === 'verify_handoff'}
      : unavailable('The handoff and workspace references are incomplete.');
  }
  if (action === 'inspect_cleanup') return item.source_type === 'runtime_result_maintenance' && reference(item.source_id)
    ? {kind: 'maintenance', id: item.source_id, result: item.result_id, workspace: item.workspace_id, agent: item.agent_id}
    : unavailable('The canonical maintenance reference is unavailable.');
  if (action === 'review_authority' && approval && reference(item.source_id)) return {kind: 'approval', id: item.source_id, workspace: item.workspace_id, decide: false};
  if (item.source_type === 'delivery_operation') return reference(item.operation_id) && reference(item.workspace_id)
    ? {kind: 'delivery', operation: item.operation_id, workspace: item.workspace_id, agent: item.agent_id}
    : unavailable('The delivery operation and workspace references are incomplete.');
  if (['message_delivery', 'runtime_pending_delivery'].includes(item.source_type)) return reference(item.message_id)
    ? {kind: 'message', id: item.message_id, workspace: item.workspace_id}
    : unavailable('The original message reference is unavailable.');
  if (['execution_operation', 'execution_result', 'handoff_result'].includes(item.source_type) &&
      reference(item.agent_id) && reference(item.executor_id) && reference(item.operation_id)) {
    return {kind: 'execution', agent: item.agent_id, executor: item.executor_id, operation: item.operation_id,
      session: item.session_id, workspace: item.workspace_id};
  }
  return unavailable('The exact canonical record cannot be opened from these references. Refresh or inspect the source in its existing page.');
}

/** Material review identity. Polls of the same request must preserve focus and drafts. */
export function approvalReviewKey(detail: Pick<ApprovalDetail, 'approval_id' | 'decision_revision' | 'action' | 'request_payload'>): string {
  const proposal = detail.request_payload?.kwargs as Record<string, unknown> | undefined;
  const identity = proposal?.approval_key;
  const key = identity && typeof identity === 'object' && !Array.isArray(identity)
    ? Object.entries(identity).sort(([a], [b]) => a.localeCompare(b)) : identity;
  return JSON.stringify([detail.approval_id, detail.decision_revision, detail.action,
    proposal?.expected_revision, proposal?.request_hash, proposal?.cas_token, key]);
}

type AttentionReadApi = Pick<typeof canonicalApi, 'approvalDetail' | 'handoffs' | 'message' |
  'agentRuntimeExecution' | 'runtimeOperationInspection' | 'inspectRuntimeMaintenance'>;

/** Only existing canonical inspection methods are accepted; opening never submits work. */
export async function readAttentionReference(api: AttentionReadApi, target: AttentionTarget, signal?: AbortSignal) {
  switch (target.kind) {
    case 'approval': {
      const record = await api.approvalDetail(target.id, signal);
      if (record.approval_id !== target.id || (target.workspace && record.workspace_id !== target.workspace))
        throw new Error('The approval no longer matches this reference.');
      return {kind: target.kind, record};
    }
    case 'handoff': {
      const value = await api.handoffs(target.workspace, {handoff_id: target.id}, signal);
      const record = value.items[0];
      if (value.items.length !== 1 || record.handoff_id !== target.id || record.workspace_id !== target.workspace)
        throw new Error('The exact handoff is no longer available in this workspace.');
      return {kind: target.kind, record};
    }
    case 'message': {
      const record = await api.message(target.id, signal);
      if (record.message_id !== target.id || (target.workspace && record.workspace_id !== target.workspace))
        throw new Error('The message no longer matches this reference.');
      return {kind: target.kind, record};
    }
    case 'execution': {
      const record = await api.agentRuntimeExecution(target.agent, target.operation, target.executor, signal);
      if (record.operation_id !== target.operation || record.scope.agent_id !== target.agent || record.scope.executor_id !== target.executor ||
          (target.session && record.scope.session_id !== target.session) || (target.workspace && record.scope.workspace_id !== target.workspace))
        throw new Error('The execution does not match the requested canonical scope.');
      return {kind: target.kind, record};
    }
    case 'delivery': {
      const value = await api.runtimeOperationInspection(target.operation, signal);
      const record = value.items[0];
      if (value.items.length !== 1 || record.operation_id !== target.operation || record.workspace_id !== target.workspace ||
          (target.agent && record.agent_id !== target.agent))
        throw new Error('The delivery operation no longer matches this reference.');
      return {kind: target.kind, record};
    }
    case 'maintenance': {
      const record = await api.inspectRuntimeMaintenance(target.id, signal);
      const receipt = record.maintenance;
      if (!receipt || receipt.maintenance_id !== target.id || (target.result && receipt.result_id !== target.result) ||
          (target.workspace && receipt.workspace_id !== target.workspace) || (target.agent && receipt.agent_id !== target.agent))
        throw new Error('The maintenance receipt no longer matches this reference.');
      return {kind: target.kind, record};
    }
    case 'unavailable': throw new Error(target.reason);
  }
}

/** Keep the reviewed generic approval revision; conflicts must be refreshed, never retried here. */
export async function decideReviewedApproval(
  api: {decideApproval: (id: string, decision: 'approve' | 'reject', justification?: string,
    response?: Record<string, unknown>, expectedDecisionRevision?: number) => Promise<unknown>},
  detail: {approval_id: string; decision_revision: number}, decision: 'approve' | 'reject',
  justification?: string, response?: Record<string, unknown>,
) {
  if (!Number.isInteger(detail.decision_revision) || detail.decision_revision < 0)
    throw new Error('The approval revision is unavailable. Refresh its canonical details.');
  return api.decideApproval(detail.approval_id, decision, justification, response, detail.decision_revision);
}
