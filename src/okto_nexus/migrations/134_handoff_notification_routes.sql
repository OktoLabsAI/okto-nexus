-- Only server-created relations establish a control notice. User text cannot.
ALTER TABLE runtime_handoff_notifications ADD COLUMN runtime_route TEXT NOT NULL DEFAULT 'conversation' CHECK(runtime_route IN ('conversation','competitive','legacy_admitted'));

-- Preserve admitted historical work for reconciliation; never infer no effect.
UPDATE runtime_handoff_notifications SET runtime_route='legacy_admitted'
WHERE event_type IN ('handoff.created','handoff.unblocked')
AND EXISTS (SELECT 1 FROM handoffs h WHERE h.handoff_id=runtime_handoff_notifications.handoff_id AND CASE WHEN json_valid(h.target) THEN json_extract(h.target,'$.strategy') END='broadcast')
AND EXISTS (SELECT 1 FROM delivery_outbox d WHERE d.message_id=runtime_handoff_notifications.message_id);

-- A waiting inbox notice without an admitted operation has no native effect.
UPDATE runtime_handoff_notifications SET runtime_route='competitive'
WHERE runtime_route='conversation' AND event_type IN ('handoff.created','handoff.unblocked')
AND EXISTS (SELECT 1 FROM handoffs h WHERE h.handoff_id=runtime_handoff_notifications.handoff_id AND CASE WHEN json_valid(h.target) THEN json_extract(h.target,'$.strategy') END='broadcast')
AND NOT EXISTS (SELECT 1 FROM delivery_outbox d WHERE d.message_id=runtime_handoff_notifications.message_id);

UPDATE runtime_pending_deliveries SET status='resolved',reason='competitive_handoff_control'
WHERE status='waiting' AND EXISTS (SELECT 1 FROM message_deliveries d JOIN runtime_handoff_notifications n USING(message_id) WHERE d.delivery_id=runtime_pending_deliveries.delivery_id AND n.runtime_route='competitive');

INSERT OR IGNORE INTO handoff_runtime_schedule(handoff_id,claim_generation,workspace_id,state,due_at)
SELECT DISTINCT h.handoff_id,h.claim_epoch,h.workspace_id,'PENDING',0 FROM handoffs h
JOIN runtime_handoff_notifications n ON n.handoff_id=h.handoff_id
WHERE h.status='OPEN' AND n.runtime_route='competitive';

CREATE INDEX idx_handoff_notification_route ON runtime_handoff_notifications(runtime_route,handoff_id);
