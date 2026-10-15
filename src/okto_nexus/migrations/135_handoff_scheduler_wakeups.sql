-- One durable generation, never a task/update per waiting handoff. Heartbeats
-- and last_seen changes do not count as authorization/configuration changes.
CREATE TRIGGER handoff_wake_defaults AFTER UPDATE OF runtime_enabled,session_policy,broadcast_handoff_auto_claim,handoff_auto_claim_epoch ON runtime_policy_defaults BEGIN UPDATE handoff_runtime_schedule_scan SET wake_generation=wake_generation+1 WHERE singleton=1; END;
CREATE TRIGGER handoff_wake_override_insert AFTER INSERT ON agent_runtime_overrides BEGIN UPDATE handoff_runtime_schedule_scan SET wake_generation=wake_generation+1 WHERE singleton=1; END;
CREATE TRIGGER handoff_wake_override_update AFTER UPDATE ON agent_runtime_overrides BEGIN UPDATE handoff_runtime_schedule_scan SET wake_generation=wake_generation+1 WHERE singleton=1; END;
CREATE TRIGGER handoff_wake_override_delete AFTER DELETE ON agent_runtime_overrides BEGIN UPDATE handoff_runtime_schedule_scan SET wake_generation=wake_generation+1 WHERE singleton=1; END;
CREATE TRIGGER handoff_wake_grant_insert AFTER INSERT ON runtime_execution_grants BEGIN UPDATE handoff_runtime_schedule_scan SET wake_generation=wake_generation+1 WHERE singleton=1; END;
CREATE TRIGGER handoff_wake_grant_update AFTER UPDATE ON runtime_execution_grants BEGIN UPDATE handoff_runtime_schedule_scan SET wake_generation=wake_generation+1 WHERE singleton=1; END;
CREATE TRIGGER handoff_wake_grant_delete AFTER DELETE ON runtime_execution_grants BEGIN UPDATE handoff_runtime_schedule_scan SET wake_generation=wake_generation+1 WHERE singleton=1; END;
CREATE TRIGGER handoff_wake_agent_policy AFTER UPDATE OF permissions,is_active,api_key_hash,comm_scope,tags,role,capabilities ON agents BEGIN UPDATE handoff_runtime_schedule_scan SET wake_generation=wake_generation+1 WHERE singleton=1; END;
CREATE TRIGGER handoff_wake_endpoint_insert AFTER INSERT ON agent_endpoints BEGIN UPDATE handoff_runtime_schedule_scan SET wake_generation=wake_generation+1 WHERE singleton=1; END;
CREATE TRIGGER handoff_wake_endpoint_update AFTER UPDATE OF enabled,activation_state,revision,selection_group,priority,profile_id ON agent_endpoints BEGIN UPDATE handoff_runtime_schedule_scan SET wake_generation=wake_generation+1 WHERE singleton=1; END;
CREATE TRIGGER handoff_wake_endpoint_delete AFTER DELETE ON agent_endpoints BEGIN UPDATE handoff_runtime_schedule_scan SET wake_generation=wake_generation+1 WHERE singleton=1; END;
CREATE TRIGGER handoff_wake_profile_update AFTER UPDATE OF enabled,revision ON runtime_profiles BEGIN UPDATE handoff_runtime_schedule_scan SET wake_generation=wake_generation+1 WHERE singleton=1; END;
CREATE TRIGGER handoff_wake_binding_insert AFTER INSERT ON execution_bindings BEGIN UPDATE handoff_runtime_schedule_scan SET wake_generation=wake_generation+1 WHERE singleton=1; END;
CREATE TRIGGER handoff_wake_binding_update AFTER UPDATE ON execution_bindings BEGIN UPDATE handoff_runtime_schedule_scan SET wake_generation=wake_generation+1 WHERE singleton=1; END;
CREATE TRIGGER handoff_wake_binding_delete AFTER DELETE ON execution_bindings BEGIN UPDATE handoff_runtime_schedule_scan SET wake_generation=wake_generation+1 WHERE singleton=1; END;
