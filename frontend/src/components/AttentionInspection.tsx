import {useEffect, useMemo, useState} from 'react';
import {api, type MessageRow, type RuntimeMaintenanceInspection, type RuntimeOperationRow} from '../api';
import type {AttentionAction, AttentionOccurrence} from '../attentionTypes';
import {attentionTarget, readAttentionReference} from '../attentionNavigation';
import {ApprovalInspection} from '../views/ApprovalsView';
import {HandoffInspection} from '../views/HandoffsView';
import {AgentActionModal} from './AgentActionModal';
import {AgentRuntimeAdministration} from './AgentRuntimeAdministration';
import {MessageDetail} from './MessageDetailModal';
import {RuntimePolicy} from './RuntimePolicy';
import {RuntimeRecovery} from './RuntimeRecovery';
import {ExternalObservationInspection} from './ExternalObservations';

export function AttentionInspection({item, action, onClose, onChanged, refreshKey}: {
  item: AttentionOccurrence; action: AttentionAction; onClose: () => void; onChanged: () => void; refreshKey?: string;
}) {
  const target = useMemo(() => attentionTarget(item, action), [item, action]);
  const targetKey = JSON.stringify(target);
  const [message, setMessage] = useState<MessageRow | null>(null);
  const [maintenance, setMaintenance] = useState<RuntimeMaintenanceInspection | null>(null);
  const [delivery, setDelivery] = useState<RuntimeOperationRow | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  useEffect(() => {setMessage(null);setMaintenance(null);setDelivery(null);setError('');}, [targetKey]);
  useEffect(() => {
    const controller = new AbortController();
    if (!['message', 'maintenance', 'delivery'].includes(target.kind)) return () => controller.abort();
    setLoading(true);setError('');
    void (async () => {
      try {
        const response = await readAttentionReference(api, target, controller.signal);
        if (controller.signal.aborted) return;
        if (response.kind === 'message') setMessage(response.record);
        if (response.kind === 'maintenance') setMaintenance(response.record);
        if (response.kind === 'delivery') setDelivery(response.record);
      } catch (failure) {
        if (!controller.signal.aborted) {setMessage(null);setMaintenance(null);setDelivery(null);setError((failure as Error).message);}
      } finally {if (!controller.signal.aborted) setLoading(false);}
    })();
    return () => controller.abort();
  }, [targetKey, refreshKey]);
  const authority = action === 'review_authority';
  const recovery = action === 'inspect_recovery' && item.kind === 'runtime_recovery_attention';
  return <AgentActionModal title="Attention · original record" wide onClose={onClose} testId="attention-inspection"
    guardChanges={authority || recovery || ['approval', 'handoff', 'execution'].includes(target.kind)}>
    <div className="space-y-4 min-w-0">
      {target.kind !== 'external_observation' && <p className="text-xs text-surface-500 break-all">{item.source_type} · {item.source_id}</p>}
      {target.kind === 'unavailable' && <p role="status">{target.reason}</p>}
      {loading && <p role="status">Loading canonical record…</p>}
      {error && <p role="alert">{error}</p>}
      {target.kind === 'external_observation' && <ExternalObservationInspection key={targetKey} target={target} refreshKey={refreshKey}
        completionEpisode={item.kind === 'external_completion_unseen' ? item.external_observation : undefined} />}
      {target.kind === 'approval' && <ApprovalInspection key={targetKey} approvalId={target.id} workspace={target.workspace}
        allowDecision={target.decide && item.freshness === 'current' && item.resolution === 'open'} onChanged={onChanged} refreshKey={refreshKey} />}
      {target.kind === 'handoff' && <HandoffInspection key={targetKey} handoffId={target.id} workspace={target.workspace}
        allowVerify={target.verify && item.freshness === 'current' && item.resolution === 'open'} onChanged={onChanged} refreshKey={refreshKey} />}
      {target.kind === 'execution' && <AgentRuntimeAdministration key={targetKey} agentId={target.agent} onClose={onClose} embedded refreshKey={refreshKey}
        initialInspection={{executorId: target.executor, operationId: target.operation, sessionId: target.session, workspaceId: target.workspace}} />}
      {target.kind === 'message' && message?.message_id === target.id && <MessageDetail message={message} />}
      {target.kind === 'delivery' && delivery?.operation_id === target.operation && <section aria-label="Canonical delivery operation" className="space-y-2 text-sm">
        <h3 className="font-semibold">Delivery operation · {delivery.state}</h3>
        <p className="break-all">{delivery.operation_id}</p><p>{delivery.reason || 'No diagnostic reason recorded.'}</p>
        <pre className="text-xs whitespace-pre-wrap break-all">{JSON.stringify(delivery, null, 2)}</pre>
      </section>}
      {target.kind === 'maintenance' && maintenance?.maintenance?.maintenance_id === target.id && <section aria-label="Canonical maintenance receipt" className="space-y-2 text-sm">
        <h3 className="font-semibold">Cleanup · {maintenance.maintenance?.status}</h3>
        <p>The productive result succeeded. This receipt concerns cleanup only.</p>
        <pre className="text-xs whitespace-pre-wrap break-all">{JSON.stringify(maintenance.maintenance, null, 2)}</pre>
        <h4 className="font-semibold">Retained result metadata</h4>
        <pre className="text-xs whitespace-pre-wrap break-all">{JSON.stringify(maintenance.results, null, 2)}</pre>
      </section>}
      {(authority || recovery) && item.agent_id && target.kind !== 'unavailable' && <section className="border-t border-surface-200 dark:border-surface-700 pt-4 space-y-4">
        <RuntimePolicy key={item.agent_id} agentId={item.agent_id} onUpdated={() => onChanged()} />
        {recovery && <RuntimeRecovery key={item.agent_id} agentId={item.agent_id} onChanged={onChanged} />}
      </section>}
      {(authority || recovery) && !item.agent_id && <p role="status">The exact agent reference for policy or recovery is unavailable.</p>}
    </div>
  </AgentActionModal>;
}
