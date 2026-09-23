ALTER TABLE runtime_results ADD COLUMN delivery_outcome TEXT CHECK(delivery_outcome IN ('success','failed','interrupted'));
ALTER TABLE harness_events ADD COLUMN delivery_outcome TEXT CHECK(delivery_outcome IN ('success','failed','interrupted'));
ALTER TABLE runtime_results ADD COLUMN relay_state TEXT NOT NULL DEFAULT 'NOT_REQUESTED';
ALTER TABLE runtime_results ADD COLUMN relay_reason TEXT;
ALTER TABLE delivery_outbox ADD COLUMN source_result_id TEXT REFERENCES runtime_results(result_id) ON DELETE RESTRICT;
CREATE INDEX runtime_outbox_source_result ON delivery_outbox(source_result_id);
