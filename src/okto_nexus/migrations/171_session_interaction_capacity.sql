-- Associate a host capacity reservation with the input's existing R4 operation.
ALTER TABLE session_interaction_inputs ADD COLUMN capacity_reservation_json TEXT;
ALTER TABLE session_interaction_inputs ADD COLUMN capacity_consumption_json TEXT;
ALTER TABLE session_interaction_inputs ADD COLUMN capacity_state TEXT
    CHECK (capacity_state IS NULL OR (
        operation_id IS NOT NULL AND capacity_reservation_json IS NOT NULL AND capacity_consumption_json IS NOT NULL
        AND capacity_state IN ('WAITING_CONSUMPTION', 'CONSUMED', 'NEEDS_RECONCILIATION', 'CANCELLED_NO_EFFECT')
    ));
