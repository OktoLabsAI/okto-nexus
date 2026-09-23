-- The new owner's immutable pre-admission journal boundary authorizes recovery
-- of already captured facts, never another external execution by the old owner.
ALTER TABLE runtime_dispatcher_owner ADD COLUMN recovery_store_id TEXT;
ALTER TABLE runtime_dispatcher_owner ADD COLUMN recovery_watermark INTEGER;
