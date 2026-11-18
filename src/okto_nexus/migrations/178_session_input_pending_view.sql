-- A submitted exact control stays in receipt history without holding the ordinary FIFO.
CREATE VIEW session_interaction_pending_inputs AS
SELECT i.*
FROM session_interaction_inputs i
LEFT JOIN session_interaction_controls c ON c.server_id=i.server_id
  AND c.executor_id=i.executor_id AND c.operation_id=i.operation_id
  AND c.session_id=i.session_id AND c.owner_generation=i.owner_generation
WHERE c.confirmed_effect_revision IS NULL OR i.status='DELIVERY_UNKNOWN'
   OR (i.status='DISPATCHING' AND NOT EXISTS (
      SELECT 1 FROM execution_dispatch_outbox d
      JOIN execution_receipts r ON r.server_id=d.server_id AND r.executor_id=d.executor_id
        AND r.operation_id=d.operation_id AND r.receipt_revision=d.last_receipt_revision
      WHERE d.server_id=i.server_id AND d.executor_id=i.executor_id AND d.operation_id=i.operation_id
        AND d.dispatch_state='DISPATCHED' AND r.stage='SUBMITTED'
   ));
