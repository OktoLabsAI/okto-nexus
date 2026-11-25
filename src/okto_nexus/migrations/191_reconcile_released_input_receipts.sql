-- Keep the original Core receipt. Correct the queue only for an already verified release.
CREATE TEMP TABLE released_input_backfill (
    input_rowid INTEGER PRIMARY KEY,
    server_id TEXT NOT NULL,
    executor_id TEXT NOT NULL,
    session_id TEXT NOT NULL
);

INSERT INTO released_input_backfill
SELECT i.rowid, i.server_id, i.executor_id, i.session_id
FROM session_interaction_inputs i
JOIN execution_sessions s USING (server_id, executor_id, session_id, owner_generation)
JOIN execution_operations o USING (server_id, executor_id, operation_id)
JOIN execution_receipts r USING (server_id, executor_id, operation_id)
WHERE i.status='DISPATCHING' AND i.possible_effect=1
  AND s.lifecycle_state='CLOSED' AND s.lease_state='CLOSED'
  AND o.session_id=i.session_id AND o.action='turn.submit' AND r.intent_hash=o.intent_hash
  AND r.stage IN ('SUBMISSION_STARTED', 'SUBMITTED') AND r.possible_effect=1
  AND r.receipt_revision=(
      SELECT max(latest.receipt_revision) FROM execution_receipts latest
      WHERE latest.server_id=i.server_id AND latest.executor_id=i.executor_id
        AND latest.operation_id=i.operation_id
  )
  AND (
      (json_extract(s.local_retirement_json, '$.process_state')='EXITED'
       AND json_extract(s.local_retirement_json, '$.owner_generation')=i.owner_generation
       AND json_extract(s.local_retirement_json, '$.opening_operation_id')=s.open_operation_id)
      OR EXISTS (
          SELECT 1 FROM execution_session_containment c
          WHERE c.server_id=i.server_id AND c.executor_id=i.executor_id AND c.session_id=i.session_id
            AND c.owner_generation=i.owner_generation AND c.opening_operation_id=s.open_operation_id
            AND c.state='RELEASED' AND json_extract(c.release_proof_json, '$.ownership.process_state')='EXITED'
      )
  );

UPDATE session_interaction_inputs SET status='DELIVERY_UNKNOWN', input_revision=input_revision+1
WHERE rowid IN (SELECT input_rowid FROM released_input_backfill);

UPDATE session_interaction_queues SET revision=revision+1
WHERE (server_id, executor_id, session_id) IN (
    SELECT server_id, executor_id, session_id FROM released_input_backfill
);

DROP TABLE released_input_backfill;
