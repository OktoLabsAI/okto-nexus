-- Durable authority and result episodes; source blocks generated from attention adapters.

INSERT INTO attention_operation_epochs(source_type,source_id,state,episode,first_detected_at,last_changed_at)
SELECT 'authority_agents',json_array(r.agent_id),'present',1,strftime('%Y-%m-%dT%H:%M:%fZ','now'),strftime('%Y-%m-%dT%H:%M:%fZ','now') FROM agents r;
CREATE TRIGGER attention_authority_agents_insert AFTER INSERT ON agents BEGIN INSERT INTO attention_operation_epochs(source_type,source_id,state,episode,first_detected_at,last_changed_at) VALUES('authority_agents',json_array(NEW.agent_id),'present',1,strftime('%Y-%m-%dT%H:%M:%fZ','now'),strftime('%Y-%m-%dT%H:%M:%fZ','now')) ON CONFLICT(source_type,source_id) DO UPDATE SET state='present',episode=attention_operation_epochs.episode+1,first_detected_at=excluded.first_detected_at,last_changed_at=excluded.last_changed_at; END;
CREATE TRIGGER attention_authority_agents_update AFTER UPDATE OF agent_id,role,capabilities,metadata,api_key_hash,is_active,permissions,preset_id,tags,comm_scope,color ON agents WHEN json_array(OLD.agent_id,OLD.role,OLD.capabilities,OLD.metadata,OLD.api_key_hash,OLD.is_active,OLD.permissions,OLD.preset_id,OLD.tags,OLD.comm_scope,OLD.color) IS NOT json_array(NEW.agent_id,NEW.role,NEW.capabilities,NEW.metadata,NEW.api_key_hash,NEW.is_active,NEW.permissions,NEW.preset_id,NEW.tags,NEW.comm_scope,NEW.color) BEGIN UPDATE attention_operation_epochs SET state='present',episode=episode+1,first_detected_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'),last_changed_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE source_type='authority_agents' AND source_id=json_array(NEW.agent_id); END;
CREATE TRIGGER attention_authority_agents_delete AFTER DELETE ON agents BEGIN UPDATE attention_operation_epochs SET state='deleted',episode=episode+1,first_detected_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'),last_changed_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE source_type='authority_agents' AND source_id=json_array(OLD.agent_id); END;

INSERT INTO attention_operation_epochs(source_type,source_id,state,episode,first_detected_at,last_changed_at)
SELECT 'authority_agent_endpoints',json_array(r.endpoint_id),'present',1,strftime('%Y-%m-%dT%H:%M:%fZ','now'),strftime('%Y-%m-%dT%H:%M:%fZ','now') FROM agent_endpoints r;
CREATE TRIGGER attention_authority_agent_endpoints_insert AFTER INSERT ON agent_endpoints BEGIN INSERT INTO attention_operation_epochs(source_type,source_id,state,episode,first_detected_at,last_changed_at) VALUES('authority_agent_endpoints',json_array(NEW.endpoint_id),'present',1,strftime('%Y-%m-%dT%H:%M:%fZ','now'),strftime('%Y-%m-%dT%H:%M:%fZ','now')) ON CONFLICT(source_type,source_id) DO UPDATE SET state='present',episode=attention_operation_epochs.episode+1,first_detected_at=excluded.first_detected_at,last_changed_at=excluded.last_changed_at; END;
CREATE TRIGGER attention_authority_agent_endpoints_update AFTER UPDATE OF endpoint_id,agent_id,workspace_id,adapter_id,protocol,contract_version,profile_id,enabled,activation_state,health,priority,selection_group,consumption,response_policy,public_config,revision ON agent_endpoints WHEN json_array(OLD.endpoint_id,OLD.agent_id,OLD.workspace_id,OLD.adapter_id,OLD.protocol,OLD.contract_version,OLD.profile_id,OLD.enabled,OLD.activation_state,OLD.health,OLD.priority,OLD.selection_group,OLD.consumption,OLD.response_policy,OLD.public_config,OLD.revision) IS NOT json_array(NEW.endpoint_id,NEW.agent_id,NEW.workspace_id,NEW.adapter_id,NEW.protocol,NEW.contract_version,NEW.profile_id,NEW.enabled,NEW.activation_state,NEW.health,NEW.priority,NEW.selection_group,NEW.consumption,NEW.response_policy,NEW.public_config,NEW.revision) BEGIN UPDATE attention_operation_epochs SET state='present',episode=episode+1,first_detected_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'),last_changed_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE source_type='authority_agent_endpoints' AND source_id=json_array(NEW.endpoint_id); END;
CREATE TRIGGER attention_authority_agent_endpoints_delete AFTER DELETE ON agent_endpoints BEGIN UPDATE attention_operation_epochs SET state='deleted',episode=episode+1,first_detected_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'),last_changed_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE source_type='authority_agent_endpoints' AND source_id=json_array(OLD.endpoint_id); END;

INSERT INTO attention_operation_epochs(source_type,source_id,state,episode,first_detected_at,last_changed_at)
SELECT 'authority_runtime_profiles',json_array(r.profile_id),'present',1,strftime('%Y-%m-%dT%H:%M:%fZ','now'),strftime('%Y-%m-%dT%H:%M:%fZ','now') FROM runtime_profiles r;
CREATE TRIGGER attention_authority_runtime_profiles_insert AFTER INSERT ON runtime_profiles BEGIN INSERT INTO attention_operation_epochs(source_type,source_id,state,episode,first_detected_at,last_changed_at) VALUES('authority_runtime_profiles',json_array(NEW.profile_id),'present',1,strftime('%Y-%m-%dT%H:%M:%fZ','now'),strftime('%Y-%m-%dT%H:%M:%fZ','now')) ON CONFLICT(source_type,source_id) DO UPDATE SET state='present',episode=attention_operation_epochs.episode+1,first_detected_at=excluded.first_detected_at,last_changed_at=excluded.last_changed_at; END;
CREATE TRIGGER attention_authority_runtime_profiles_update AFTER UPDATE OF profile_id,adapter_id,config,secret_refs,inherit_ambient,enabled,revision,launch_revision ON runtime_profiles WHEN json_array(OLD.profile_id,OLD.adapter_id,OLD.config,OLD.secret_refs,OLD.inherit_ambient,OLD.enabled,OLD.revision,OLD.launch_revision) IS NOT json_array(NEW.profile_id,NEW.adapter_id,NEW.config,NEW.secret_refs,NEW.inherit_ambient,NEW.enabled,NEW.revision,NEW.launch_revision) BEGIN UPDATE attention_operation_epochs SET state='present',episode=episode+1,first_detected_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'),last_changed_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE source_type='authority_runtime_profiles' AND source_id=json_array(NEW.profile_id); END;
CREATE TRIGGER attention_authority_runtime_profiles_delete AFTER DELETE ON runtime_profiles BEGIN UPDATE attention_operation_epochs SET state='deleted',episode=episode+1,first_detected_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'),last_changed_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE source_type='authority_runtime_profiles' AND source_id=json_array(OLD.profile_id); END;

INSERT INTO attention_operation_epochs(source_type,source_id,state,episode,first_detected_at,last_changed_at)
SELECT 'authority_agent_runtime_overrides',json_array(r.agent_id),'present',1,strftime('%Y-%m-%dT%H:%M:%fZ','now'),strftime('%Y-%m-%dT%H:%M:%fZ','now') FROM agent_runtime_overrides r;
CREATE TRIGGER attention_authority_agent_runtime_overrides_insert AFTER INSERT ON agent_runtime_overrides BEGIN INSERT INTO attention_operation_epochs(source_type,source_id,state,episode,first_detected_at,last_changed_at) VALUES('authority_agent_runtime_overrides',json_array(NEW.agent_id),'present',1,strftime('%Y-%m-%dT%H:%M:%fZ','now'),strftime('%Y-%m-%dT%H:%M:%fZ','now')) ON CONFLICT(source_type,source_id) DO UPDATE SET state='present',episode=attention_operation_epochs.episode+1,first_detected_at=excluded.first_detected_at,last_changed_at=excluded.last_changed_at; END;
CREATE TRIGGER attention_authority_agent_runtime_overrides_update AFTER UPDATE OF agent_id,runtime_enabled,session_policy,broadcast_handoff_auto_claim,handoff_auto_claim_epoch ON agent_runtime_overrides WHEN json_array(OLD.agent_id,OLD.runtime_enabled,OLD.session_policy,OLD.broadcast_handoff_auto_claim,OLD.handoff_auto_claim_epoch) IS NOT json_array(NEW.agent_id,NEW.runtime_enabled,NEW.session_policy,NEW.broadcast_handoff_auto_claim,NEW.handoff_auto_claim_epoch) BEGIN UPDATE attention_operation_epochs SET state='present',episode=episode+1,first_detected_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'),last_changed_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE source_type='authority_agent_runtime_overrides' AND source_id=json_array(NEW.agent_id); END;
CREATE TRIGGER attention_authority_agent_runtime_overrides_delete AFTER DELETE ON agent_runtime_overrides BEGIN UPDATE attention_operation_epochs SET state='deleted',episode=episode+1,first_detected_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'),last_changed_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE source_type='authority_agent_runtime_overrides' AND source_id=json_array(OLD.agent_id); END;

INSERT INTO attention_operation_epochs(source_type,source_id,state,episode,first_detected_at,last_changed_at)
SELECT 'authority_agent_runtime_policy_epochs',json_array(r.agent_id),'present',1,strftime('%Y-%m-%dT%H:%M:%fZ','now'),strftime('%Y-%m-%dT%H:%M:%fZ','now') FROM agent_runtime_policy_epochs r;
CREATE TRIGGER attention_authority_agent_runtime_policy_epochs_insert AFTER INSERT ON agent_runtime_policy_epochs BEGIN INSERT INTO attention_operation_epochs(source_type,source_id,state,episode,first_detected_at,last_changed_at) VALUES('authority_agent_runtime_policy_epochs',json_array(NEW.agent_id),'present',1,strftime('%Y-%m-%dT%H:%M:%fZ','now'),strftime('%Y-%m-%dT%H:%M:%fZ','now')) ON CONFLICT(source_type,source_id) DO UPDATE SET state='present',episode=attention_operation_epochs.episode+1,first_detected_at=excluded.first_detected_at,last_changed_at=excluded.last_changed_at; END;
CREATE TRIGGER attention_authority_agent_runtime_policy_epochs_update AFTER UPDATE OF agent_id,epoch ON agent_runtime_policy_epochs WHEN json_array(OLD.agent_id,OLD.epoch) IS NOT json_array(NEW.agent_id,NEW.epoch) BEGIN UPDATE attention_operation_epochs SET state='present',episode=episode+1,first_detected_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'),last_changed_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE source_type='authority_agent_runtime_policy_epochs' AND source_id=json_array(NEW.agent_id); END;
CREATE TRIGGER attention_authority_agent_runtime_policy_epochs_delete AFTER DELETE ON agent_runtime_policy_epochs BEGIN UPDATE attention_operation_epochs SET state='deleted',episode=episode+1,first_detected_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'),last_changed_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE source_type='authority_agent_runtime_policy_epochs' AND source_id=json_array(OLD.agent_id); END;

INSERT INTO attention_operation_epochs(source_type,source_id,state,episode,first_detected_at,last_changed_at)
SELECT 'authority_runtime_execution_grants',json_array(r.grant_id),'present',1,strftime('%Y-%m-%dT%H:%M:%fZ','now'),strftime('%Y-%m-%dT%H:%M:%fZ','now') FROM runtime_execution_grants r;
CREATE TRIGGER attention_authority_runtime_execution_grants_insert AFTER INSERT ON runtime_execution_grants BEGIN INSERT INTO attention_operation_epochs(source_type,source_id,state,episode,first_detected_at,last_changed_at) VALUES('authority_runtime_execution_grants',json_array(NEW.grant_id),'present',1,strftime('%Y-%m-%dT%H:%M:%fZ','now'),strftime('%Y-%m-%dT%H:%M:%fZ','now')) ON CONFLICT(source_type,source_id) DO UPDATE SET state='present',episode=attention_operation_epochs.episode+1,first_detected_at=excluded.first_detected_at,last_changed_at=excluded.last_changed_at; END;
CREATE TRIGGER attention_authority_runtime_execution_grants_update AFTER UPDATE OF grant_id,actor_agent_id,credential_binding,represented_agent_id,endpoint_id,workspace_id,profile_revision,actions,expires_at,no_expiry,unlimited_actions,used_executions,max_executions,revoked_at,revision ON runtime_execution_grants WHEN json_array(OLD.grant_id,OLD.actor_agent_id,OLD.credential_binding,OLD.represented_agent_id,OLD.endpoint_id,OLD.workspace_id,OLD.profile_revision,OLD.actions,OLD.expires_at,OLD.no_expiry,OLD.unlimited_actions,OLD.used_executions,OLD.max_executions,OLD.revoked_at,OLD.revision) IS NOT json_array(NEW.grant_id,NEW.actor_agent_id,NEW.credential_binding,NEW.represented_agent_id,NEW.endpoint_id,NEW.workspace_id,NEW.profile_revision,NEW.actions,NEW.expires_at,NEW.no_expiry,NEW.unlimited_actions,NEW.used_executions,NEW.max_executions,NEW.revoked_at,NEW.revision) BEGIN UPDATE attention_operation_epochs SET state='present',episode=episode+1,first_detected_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'),last_changed_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE source_type='authority_runtime_execution_grants' AND source_id=json_array(NEW.grant_id); END;
CREATE TRIGGER attention_authority_runtime_execution_grants_delete AFTER DELETE ON runtime_execution_grants BEGIN UPDATE attention_operation_epochs SET state='deleted',episode=episode+1,first_detected_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'),last_changed_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE source_type='authority_runtime_execution_grants' AND source_id=json_array(OLD.grant_id); END;

INSERT INTO attention_operation_epochs(source_type,source_id,state,episode,first_detected_at,last_changed_at)
SELECT 'authority_handoff_authorization_receipts',json_array(r.handoff_id),'present',1,strftime('%Y-%m-%dT%H:%M:%fZ','now'),strftime('%Y-%m-%dT%H:%M:%fZ','now') FROM handoff_authorization_receipts r;
CREATE TRIGGER attention_authority_handoff_authorization_receipts_insert AFTER INSERT ON handoff_authorization_receipts BEGIN INSERT INTO attention_operation_epochs(source_type,source_id,state,episode,first_detected_at,last_changed_at) VALUES('authority_handoff_authorization_receipts',json_array(NEW.handoff_id),'present',1,strftime('%Y-%m-%dT%H:%M:%fZ','now'),strftime('%Y-%m-%dT%H:%M:%fZ','now')) ON CONFLICT(source_type,source_id) DO UPDATE SET state='present',episode=attention_operation_epochs.episode+1,first_detected_at=excluded.first_detected_at,last_changed_at=excluded.last_changed_at; END;
CREATE TRIGGER attention_authority_handoff_authorization_receipts_update AFTER UPDATE OF handoff_id,creator_policy_revision,hitl_enabled ON handoff_authorization_receipts WHEN json_array(OLD.handoff_id,OLD.creator_policy_revision,OLD.hitl_enabled) IS NOT json_array(NEW.handoff_id,NEW.creator_policy_revision,NEW.hitl_enabled) BEGIN UPDATE attention_operation_epochs SET state='present',episode=episode+1,first_detected_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'),last_changed_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE source_type='authority_handoff_authorization_receipts' AND source_id=json_array(NEW.handoff_id); END;
CREATE TRIGGER attention_authority_handoff_authorization_receipts_delete AFTER DELETE ON handoff_authorization_receipts BEGIN UPDATE attention_operation_epochs SET state='deleted',episode=episode+1,first_detected_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'),last_changed_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE source_type='authority_handoff_authorization_receipts' AND source_id=json_array(OLD.handoff_id); END;

INSERT INTO attention_operation_epochs(source_type,source_id,state,episode,first_detected_at,last_changed_at)
SELECT 'authority_harness_sessions',json_array(r.session_id),'present',1,strftime('%Y-%m-%dT%H:%M:%fZ','now'),strftime('%Y-%m-%dT%H:%M:%fZ','now') FROM harness_sessions r;
CREATE TRIGGER attention_authority_harness_sessions_insert AFTER INSERT ON harness_sessions BEGIN INSERT INTO attention_operation_epochs(source_type,source_id,state,episode,first_detected_at,last_changed_at) VALUES('authority_harness_sessions',json_array(NEW.session_id),'present',1,strftime('%Y-%m-%dT%H:%M:%fZ','now'),strftime('%Y-%m-%dT%H:%M:%fZ','now')) ON CONFLICT(source_type,source_id) DO UPDATE SET state='present',episode=attention_operation_epochs.episode+1,first_detected_at=excluded.first_detected_at,last_changed_at=excluded.last_changed_at; END;
CREATE TRIGGER attention_authority_harness_sessions_update AFTER UPDATE OF session_id,runtime_profile_revision ON harness_sessions WHEN json_array(OLD.session_id,OLD.runtime_profile_revision) IS NOT json_array(NEW.session_id,NEW.runtime_profile_revision) BEGIN UPDATE attention_operation_epochs SET state='present',episode=episode+1,first_detected_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'),last_changed_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE source_type='authority_harness_sessions' AND source_id=json_array(NEW.session_id); END;
CREATE TRIGGER attention_authority_harness_sessions_delete AFTER DELETE ON harness_sessions BEGIN UPDATE attention_operation_epochs SET state='deleted',episode=episode+1,first_detected_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'),last_changed_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE source_type='authority_harness_sessions' AND source_id=json_array(OLD.session_id); END;

INSERT INTO attention_operation_epochs(source_type,source_id,state,episode,first_detected_at,last_changed_at)
SELECT 'authority_runtime_boot_bindings',json_array(r.endpoint_id),'present',1,strftime('%Y-%m-%dT%H:%M:%fZ','now'),strftime('%Y-%m-%dT%H:%M:%fZ','now') FROM runtime_boot_bindings r;
CREATE TRIGGER attention_authority_runtime_boot_bindings_insert AFTER INSERT ON runtime_boot_bindings BEGIN INSERT INTO attention_operation_epochs(source_type,source_id,state,episode,first_detected_at,last_changed_at) VALUES('authority_runtime_boot_bindings',json_array(NEW.endpoint_id),'present',1,strftime('%Y-%m-%dT%H:%M:%fZ','now'),strftime('%Y-%m-%dT%H:%M:%fZ','now')) ON CONFLICT(source_type,source_id) DO UPDATE SET state='present',episode=attention_operation_epochs.episode+1,first_detected_at=excluded.first_detected_at,last_changed_at=excluded.last_changed_at; END;
CREATE TRIGGER attention_authority_runtime_boot_bindings_update AFTER UPDATE OF endpoint_id,enabled,endpoint_revision,profile_revision,issuer_agent_id,issuer_credential_binding,revision ON runtime_boot_bindings WHEN json_array(OLD.endpoint_id,OLD.enabled,OLD.endpoint_revision,OLD.profile_revision,OLD.issuer_agent_id,OLD.issuer_credential_binding,OLD.revision) IS NOT json_array(NEW.endpoint_id,NEW.enabled,NEW.endpoint_revision,NEW.profile_revision,NEW.issuer_agent_id,NEW.issuer_credential_binding,NEW.revision) BEGIN UPDATE attention_operation_epochs SET state='present',episode=episode+1,first_detected_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'),last_changed_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE source_type='authority_runtime_boot_bindings' AND source_id=json_array(NEW.endpoint_id); END;
CREATE TRIGGER attention_authority_runtime_boot_bindings_delete AFTER DELETE ON runtime_boot_bindings BEGIN UPDATE attention_operation_epochs SET state='deleted',episode=episode+1,first_detected_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'),last_changed_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE source_type='authority_runtime_boot_bindings' AND source_id=json_array(OLD.endpoint_id); END;

INSERT INTO attention_operation_epochs(source_type,source_id,state,episode,first_detected_at,last_changed_at)
SELECT 'authority_execution_agent_revisions',json_array(r.server_id,r.agent_id),'present',1,strftime('%Y-%m-%dT%H:%M:%fZ','now'),strftime('%Y-%m-%dT%H:%M:%fZ','now') FROM execution_agent_revisions r;
CREATE TRIGGER attention_authority_execution_agent_revisions_insert AFTER INSERT ON execution_agent_revisions BEGIN INSERT INTO attention_operation_epochs(source_type,source_id,state,episode,first_detected_at,last_changed_at) VALUES('authority_execution_agent_revisions',json_array(NEW.server_id,NEW.agent_id),'present',1,strftime('%Y-%m-%dT%H:%M:%fZ','now'),strftime('%Y-%m-%dT%H:%M:%fZ','now')) ON CONFLICT(source_type,source_id) DO UPDATE SET state='present',episode=attention_operation_epochs.episode+1,first_detected_at=excluded.first_detected_at,last_changed_at=excluded.last_changed_at; END;
CREATE TRIGGER attention_authority_execution_agent_revisions_update AFTER UPDATE OF server_id,agent_id,authorization_revision,configuration_revision,credential_epoch ON execution_agent_revisions WHEN json_array(OLD.server_id,OLD.agent_id,OLD.authorization_revision,OLD.configuration_revision,OLD.credential_epoch) IS NOT json_array(NEW.server_id,NEW.agent_id,NEW.authorization_revision,NEW.configuration_revision,NEW.credential_epoch) BEGIN UPDATE attention_operation_epochs SET state='present',episode=episode+1,first_detected_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'),last_changed_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE source_type='authority_execution_agent_revisions' AND source_id=json_array(NEW.server_id,NEW.agent_id); END;
CREATE TRIGGER attention_authority_execution_agent_revisions_delete AFTER DELETE ON execution_agent_revisions BEGIN UPDATE attention_operation_epochs SET state='deleted',episode=episode+1,first_detected_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'),last_changed_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE source_type='authority_execution_agent_revisions' AND source_id=json_array(OLD.server_id,OLD.agent_id); END;

INSERT INTO attention_operation_epochs(source_type,source_id,state,episode,first_detected_at,last_changed_at)
SELECT 'authority_execution_bindings',json_array(r.server_id,r.executor_id,r.binding_id),'present',1,strftime('%Y-%m-%dT%H:%M:%fZ','now'),strftime('%Y-%m-%dT%H:%M:%fZ','now') FROM execution_bindings r;
CREATE TRIGGER attention_authority_execution_bindings_insert AFTER INSERT ON execution_bindings BEGIN INSERT INTO attention_operation_epochs(source_type,source_id,state,episode,first_detected_at,last_changed_at) VALUES('authority_execution_bindings',json_array(NEW.server_id,NEW.executor_id,NEW.binding_id),'present',1,strftime('%Y-%m-%dT%H:%M:%fZ','now'),strftime('%Y-%m-%dT%H:%M:%fZ','now')) ON CONFLICT(source_type,source_id) DO UPDATE SET state='present',episode=attention_operation_epochs.episode+1,first_detected_at=excluded.first_detected_at,last_changed_at=excluded.last_changed_at; END;
CREATE TRIGGER attention_authority_execution_bindings_update AFTER UPDATE OF server_id,executor_id,binding_id,endpoint_id,workspace_binding_id,binding_revision,realization_ref,realization_revision ON execution_bindings WHEN json_array(OLD.server_id,OLD.executor_id,OLD.binding_id,OLD.endpoint_id,OLD.workspace_binding_id,OLD.binding_revision,OLD.realization_ref,OLD.realization_revision) IS NOT json_array(NEW.server_id,NEW.executor_id,NEW.binding_id,NEW.endpoint_id,NEW.workspace_binding_id,NEW.binding_revision,NEW.realization_ref,NEW.realization_revision) BEGIN UPDATE attention_operation_epochs SET state='present',episode=episode+1,first_detected_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'),last_changed_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE source_type='authority_execution_bindings' AND source_id=json_array(NEW.server_id,NEW.executor_id,NEW.binding_id); END;
CREATE TRIGGER attention_authority_execution_bindings_delete AFTER DELETE ON execution_bindings BEGIN UPDATE attention_operation_epochs SET state='deleted',episode=episode+1,first_detected_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'),last_changed_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE source_type='authority_execution_bindings' AND source_id=json_array(OLD.server_id,OLD.executor_id,OLD.binding_id); END;

INSERT INTO attention_operation_epochs(source_type,source_id,state,episode,first_detected_at,last_changed_at)
SELECT 'authority_execution_executors',json_array(r.server_id,r.executor_id),'present',1,strftime('%Y-%m-%dT%H:%M:%fZ','now'),strftime('%Y-%m-%dT%H:%M:%fZ','now') FROM execution_executors r;
CREATE TRIGGER attention_authority_execution_executors_insert AFTER INSERT ON execution_executors BEGIN INSERT INTO attention_operation_epochs(source_type,source_id,state,episode,first_detected_at,last_changed_at) VALUES('authority_execution_executors',json_array(NEW.server_id,NEW.executor_id),'present',1,strftime('%Y-%m-%dT%H:%M:%fZ','now'),strftime('%Y-%m-%dT%H:%M:%fZ','now')) ON CONFLICT(source_type,source_id) DO UPDATE SET state='present',episode=attention_operation_epochs.episode+1,first_detected_at=excluded.first_detected_at,last_changed_at=excluded.last_changed_at; END;
CREATE TRIGGER attention_authority_execution_executors_update AFTER UPDATE OF server_id,executor_id,kind,revoked_at,generation,owner_instance_id ON execution_executors WHEN json_array(OLD.server_id,OLD.executor_id,OLD.kind,OLD.revoked_at,OLD.generation,OLD.owner_instance_id) IS NOT json_array(NEW.server_id,NEW.executor_id,NEW.kind,NEW.revoked_at,NEW.generation,NEW.owner_instance_id) BEGIN UPDATE attention_operation_epochs SET state='present',episode=episode+1,first_detected_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'),last_changed_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE source_type='authority_execution_executors' AND source_id=json_array(NEW.server_id,NEW.executor_id); END;
CREATE TRIGGER attention_authority_execution_executors_delete AFTER DELETE ON execution_executors BEGIN UPDATE attention_operation_epochs SET state='deleted',episode=episode+1,first_detected_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'),last_changed_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE source_type='authority_execution_executors' AND source_id=json_array(OLD.server_id,OLD.executor_id); END;

INSERT INTO attention_operation_epochs(source_type,source_id,state,episode,first_detected_at,last_changed_at)
SELECT 'authority_execution_workspace_bindings',json_array(r.server_id,r.executor_id,r.workspace_binding_id),'present',1,strftime('%Y-%m-%dT%H:%M:%fZ','now'),strftime('%Y-%m-%dT%H:%M:%fZ','now') FROM execution_workspace_bindings r;
CREATE TRIGGER attention_authority_execution_workspace_bindings_insert AFTER INSERT ON execution_workspace_bindings BEGIN INSERT INTO attention_operation_epochs(source_type,source_id,state,episode,first_detected_at,last_changed_at) VALUES('authority_execution_workspace_bindings',json_array(NEW.server_id,NEW.executor_id,NEW.workspace_binding_id),'present',1,strftime('%Y-%m-%dT%H:%M:%fZ','now'),strftime('%Y-%m-%dT%H:%M:%fZ','now')) ON CONFLICT(source_type,source_id) DO UPDATE SET state='present',episode=attention_operation_epochs.episode+1,first_detected_at=excluded.first_detected_at,last_changed_at=excluded.last_changed_at; END;
CREATE TRIGGER attention_authority_execution_workspace_bindings_update AFTER UPDATE OF server_id,executor_id,workspace_binding_id,workspace_id,status ON execution_workspace_bindings WHEN json_array(OLD.server_id,OLD.executor_id,OLD.workspace_binding_id,OLD.workspace_id,OLD.status) IS NOT json_array(NEW.server_id,NEW.executor_id,NEW.workspace_binding_id,NEW.workspace_id,NEW.status) BEGIN UPDATE attention_operation_epochs SET state='present',episode=episode+1,first_detected_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'),last_changed_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE source_type='authority_execution_workspace_bindings' AND source_id=json_array(NEW.server_id,NEW.executor_id,NEW.workspace_binding_id); END;
CREATE TRIGGER attention_authority_execution_workspace_bindings_delete AFTER DELETE ON execution_workspace_bindings BEGIN UPDATE attention_operation_epochs SET state='deleted',episode=episode+1,first_detected_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'),last_changed_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE source_type='authority_execution_workspace_bindings' AND source_id=json_array(OLD.server_id,OLD.executor_id,OLD.workspace_binding_id); END;

INSERT INTO attention_operation_epochs(source_type,source_id,state,episode,first_detected_at,last_changed_at)
SELECT 'authority_execution_realizations',json_array(r.server_id,r.executor_id,r.realization_ref),'present',1,strftime('%Y-%m-%dT%H:%M:%fZ','now'),strftime('%Y-%m-%dT%H:%M:%fZ','now') FROM execution_realizations r;
CREATE TRIGGER attention_authority_execution_realizations_insert AFTER INSERT ON execution_realizations BEGIN INSERT INTO attention_operation_epochs(source_type,source_id,state,episode,first_detected_at,last_changed_at) VALUES('authority_execution_realizations',json_array(NEW.server_id,NEW.executor_id,NEW.realization_ref),'present',1,strftime('%Y-%m-%dT%H:%M:%fZ','now'),strftime('%Y-%m-%dT%H:%M:%fZ','now')) ON CONFLICT(source_type,source_id) DO UPDATE SET state='present',episode=attention_operation_epochs.episode+1,first_detected_at=excluded.first_detected_at,last_changed_at=excluded.last_changed_at; END;
CREATE TRIGGER attention_authority_execution_realizations_update AFTER UPDATE OF server_id,executor_id,realization_ref,workspace_binding_id,subject_agent_id,status,revision ON execution_realizations WHEN json_array(OLD.server_id,OLD.executor_id,OLD.realization_ref,OLD.workspace_binding_id,OLD.subject_agent_id,OLD.status,OLD.revision) IS NOT json_array(NEW.server_id,NEW.executor_id,NEW.realization_ref,NEW.workspace_binding_id,NEW.subject_agent_id,NEW.status,NEW.revision) BEGIN UPDATE attention_operation_epochs SET state='present',episode=episode+1,first_detected_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'),last_changed_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE source_type='authority_execution_realizations' AND source_id=json_array(NEW.server_id,NEW.executor_id,NEW.realization_ref); END;
CREATE TRIGGER attention_authority_execution_realizations_delete AFTER DELETE ON execution_realizations BEGIN UPDATE attention_operation_epochs SET state='deleted',episode=episode+1,first_detected_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'),last_changed_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE source_type='authority_execution_realizations' AND source_id=json_array(OLD.server_id,OLD.executor_id,OLD.realization_ref); END;

INSERT INTO attention_operation_epochs(source_type,source_id,state,episode,first_detected_at,last_changed_at)
SELECT 'authority_execution_sessions',json_array(r.server_id,r.executor_id,r.session_id),'present',1,strftime('%Y-%m-%dT%H:%M:%fZ','now'),strftime('%Y-%m-%dT%H:%M:%fZ','now') FROM execution_sessions r;
CREATE TRIGGER attention_authority_execution_sessions_insert AFTER INSERT ON execution_sessions BEGIN INSERT INTO attention_operation_epochs(source_type,source_id,state,episode,first_detected_at,last_changed_at) VALUES('authority_execution_sessions',json_array(NEW.server_id,NEW.executor_id,NEW.session_id),'present',1,strftime('%Y-%m-%dT%H:%M:%fZ','now'),strftime('%Y-%m-%dT%H:%M:%fZ','now')) ON CONFLICT(source_type,source_id) DO UPDATE SET state='present',episode=attention_operation_epochs.episode+1,first_detected_at=excluded.first_detected_at,last_changed_at=excluded.last_changed_at; END;
CREATE TRIGGER attention_authority_execution_sessions_update AFTER UPDATE OF server_id,executor_id,session_id,binding_id,workspace_id,workspace_binding_id,open_operation_id,owner_generation,lifecycle_state,lease_state ON execution_sessions WHEN json_array(OLD.server_id,OLD.executor_id,OLD.session_id,OLD.binding_id,OLD.workspace_id,OLD.workspace_binding_id,OLD.open_operation_id,OLD.owner_generation,OLD.lifecycle_state,OLD.lease_state) IS NOT json_array(NEW.server_id,NEW.executor_id,NEW.session_id,NEW.binding_id,NEW.workspace_id,NEW.workspace_binding_id,NEW.open_operation_id,NEW.owner_generation,NEW.lifecycle_state,NEW.lease_state) BEGIN UPDATE attention_operation_epochs SET state='present',episode=episode+1,first_detected_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'),last_changed_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE source_type='authority_execution_sessions' AND source_id=json_array(NEW.server_id,NEW.executor_id,NEW.session_id); END;
CREATE TRIGGER attention_authority_execution_sessions_delete AFTER DELETE ON execution_sessions BEGIN UPDATE attention_operation_epochs SET state='deleted',episode=episode+1,first_detected_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'),last_changed_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE source_type='authority_execution_sessions' AND source_id=json_array(OLD.server_id,OLD.executor_id,OLD.session_id); END;

INSERT INTO attention_operation_epochs(source_type,source_id,state,episode,first_detected_at,last_changed_at)
SELECT 'authority_execution_session_capabilities',json_array(r.capability_id),'present',1,strftime('%Y-%m-%dT%H:%M:%fZ','now'),strftime('%Y-%m-%dT%H:%M:%fZ','now') FROM execution_session_capabilities r;
CREATE TRIGGER attention_authority_execution_session_capabilities_insert AFTER INSERT ON execution_session_capabilities BEGIN INSERT INTO attention_operation_epochs(source_type,source_id,state,episode,first_detected_at,last_changed_at) VALUES('authority_execution_session_capabilities',json_array(NEW.capability_id),'present',1,strftime('%Y-%m-%dT%H:%M:%fZ','now'),strftime('%Y-%m-%dT%H:%M:%fZ','now')) ON CONFLICT(source_type,source_id) DO UPDATE SET state='present',episode=attention_operation_epochs.episode+1,first_detected_at=excluded.first_detected_at,last_changed_at=excluded.last_changed_at; END;
CREATE TRIGGER attention_authority_execution_session_capabilities_update AFTER UPDATE OF capability_id,audience,scope_json,actions_json,revoked_at,valid_until_server,source_grant_id,source_grant_revision ON execution_session_capabilities WHEN json_array(OLD.capability_id,OLD.audience,OLD.scope_json,OLD.actions_json,OLD.revoked_at,OLD.valid_until_server,OLD.source_grant_id,OLD.source_grant_revision) IS NOT json_array(NEW.capability_id,NEW.audience,NEW.scope_json,NEW.actions_json,NEW.revoked_at,NEW.valid_until_server,NEW.source_grant_id,NEW.source_grant_revision) BEGIN UPDATE attention_operation_epochs SET state='present',episode=episode+1,first_detected_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'),last_changed_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE source_type='authority_execution_session_capabilities' AND source_id=json_array(NEW.capability_id); END;
CREATE TRIGGER attention_authority_execution_session_capabilities_delete AFTER DELETE ON execution_session_capabilities BEGIN UPDATE attention_operation_epochs SET state='deleted',episode=episode+1,first_detected_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'),last_changed_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE source_type='authority_execution_session_capabilities' AND source_id=json_array(OLD.capability_id); END;

INSERT INTO attention_operation_epochs(source_type,source_id,state,episode,first_detected_at,last_changed_at)
SELECT 'authority_agent_connection_methods',json_array(r.agent_id,r.method),'present',1,strftime('%Y-%m-%dT%H:%M:%fZ','now'),strftime('%Y-%m-%dT%H:%M:%fZ','now') FROM agent_connection_methods r;
CREATE TRIGGER attention_authority_agent_connection_methods_insert AFTER INSERT ON agent_connection_methods BEGIN INSERT INTO attention_operation_epochs(source_type,source_id,state,episode,first_detected_at,last_changed_at) VALUES('authority_agent_connection_methods',json_array(NEW.agent_id,NEW.method),'present',1,strftime('%Y-%m-%dT%H:%M:%fZ','now'),strftime('%Y-%m-%dT%H:%M:%fZ','now')) ON CONFLICT(source_type,source_id) DO UPDATE SET state='present',episode=attention_operation_epochs.episode+1,first_detected_at=excluded.first_detected_at,last_changed_at=excluded.last_changed_at; END;
CREATE TRIGGER attention_authority_agent_connection_methods_update AFTER UPDATE OF agent_id,method,enabled ON agent_connection_methods WHEN json_array(OLD.agent_id,OLD.method,OLD.enabled) IS NOT json_array(NEW.agent_id,NEW.method,NEW.enabled) BEGIN UPDATE attention_operation_epochs SET state='present',episode=episode+1,first_detected_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'),last_changed_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE source_type='authority_agent_connection_methods' AND source_id=json_array(NEW.agent_id,NEW.method); END;
CREATE TRIGGER attention_authority_agent_connection_methods_delete AFTER DELETE ON agent_connection_methods BEGIN UPDATE attention_operation_epochs SET state='deleted',episode=episode+1,first_detected_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'),last_changed_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE source_type='authority_agent_connection_methods' AND source_id=json_array(OLD.agent_id,OLD.method); END;

INSERT INTO attention_operation_epochs(source_type,source_id,state,episode,first_detected_at,last_changed_at)
SELECT 'authority_agent_execution_policies',json_array(r.agent_id),'present',1,strftime('%Y-%m-%dT%H:%M:%fZ','now'),strftime('%Y-%m-%dT%H:%M:%fZ','now') FROM agent_execution_policies r;
CREATE TRIGGER attention_authority_agent_execution_policies_insert AFTER INSERT ON agent_execution_policies BEGIN INSERT INTO attention_operation_epochs(source_type,source_id,state,episode,first_detected_at,last_changed_at) VALUES('authority_agent_execution_policies',json_array(NEW.agent_id),'present',1,strftime('%Y-%m-%dT%H:%M:%fZ','now'),strftime('%Y-%m-%dT%H:%M:%fZ','now')) ON CONFLICT(source_type,source_id) DO UPDATE SET state='present',episode=attention_operation_epochs.episode+1,first_detected_at=excluded.first_detected_at,last_changed_at=excluded.last_changed_at; END;
CREATE TRIGGER attention_authority_agent_execution_policies_update AFTER UPDATE OF agent_id,execution_location,local_adapter_id,revision ON agent_execution_policies WHEN json_array(OLD.agent_id,OLD.execution_location,OLD.local_adapter_id,OLD.revision) IS NOT json_array(NEW.agent_id,NEW.execution_location,NEW.local_adapter_id,NEW.revision) BEGIN UPDATE attention_operation_epochs SET state='present',episode=episode+1,first_detected_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'),last_changed_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE source_type='authority_agent_execution_policies' AND source_id=json_array(NEW.agent_id); END;
CREATE TRIGGER attention_authority_agent_execution_policies_delete AFTER DELETE ON agent_execution_policies BEGIN UPDATE attention_operation_epochs SET state='deleted',episode=episode+1,first_detected_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'),last_changed_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE source_type='authority_agent_execution_policies' AND source_id=json_array(OLD.agent_id); END;

INSERT INTO attention_operation_epochs(source_type,source_id,state,episode,first_detected_at,last_changed_at)
SELECT 'authority_runtime_policy_defaults',json_array(r.singleton),'present',1,strftime('%Y-%m-%dT%H:%M:%fZ','now'),strftime('%Y-%m-%dT%H:%M:%fZ','now') FROM runtime_policy_defaults r;
CREATE TRIGGER attention_authority_runtime_policy_defaults_insert AFTER INSERT ON runtime_policy_defaults BEGIN INSERT INTO attention_operation_epochs(source_type,source_id,state,episode,first_detected_at,last_changed_at) VALUES('authority_runtime_policy_defaults',json_array(NEW.singleton),'present',1,strftime('%Y-%m-%dT%H:%M:%fZ','now'),strftime('%Y-%m-%dT%H:%M:%fZ','now')) ON CONFLICT(source_type,source_id) DO UPDATE SET state='present',episode=attention_operation_epochs.episode+1,first_detected_at=excluded.first_detected_at,last_changed_at=excluded.last_changed_at; END;
CREATE TRIGGER attention_authority_runtime_policy_defaults_update AFTER UPDATE OF singleton,runtime_enabled,session_policy,broadcast_handoff_auto_claim,handoff_auto_claim_epoch ON runtime_policy_defaults WHEN json_array(OLD.singleton,OLD.runtime_enabled,OLD.session_policy,OLD.broadcast_handoff_auto_claim,OLD.handoff_auto_claim_epoch) IS NOT json_array(NEW.singleton,NEW.runtime_enabled,NEW.session_policy,NEW.broadcast_handoff_auto_claim,NEW.handoff_auto_claim_epoch) BEGIN UPDATE attention_operation_epochs SET state='present',episode=episode+1,first_detected_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'),last_changed_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE source_type='authority_runtime_policy_defaults' AND source_id=json_array(NEW.singleton); END;
CREATE TRIGGER attention_authority_runtime_policy_defaults_delete AFTER DELETE ON runtime_policy_defaults BEGIN UPDATE attention_operation_epochs SET state='deleted',episode=episode+1,first_detected_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'),last_changed_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE source_type='authority_runtime_policy_defaults' AND source_id=json_array(OLD.singleton); END;

INSERT INTO attention_operation_epochs(source_type,source_id,state,episode,first_detected_at,last_changed_at)
SELECT 'authority_agent_policy_bindings',json_array(r.agent_id,r.position),'present',1,strftime('%Y-%m-%dT%H:%M:%fZ','now'),strftime('%Y-%m-%dT%H:%M:%fZ','now') FROM agent_policy_bindings r;
CREATE TRIGGER attention_authority_agent_policy_bindings_insert AFTER INSERT ON agent_policy_bindings BEGIN INSERT INTO attention_operation_epochs(source_type,source_id,state,episode,first_detected_at,last_changed_at) VALUES('authority_agent_policy_bindings',json_array(NEW.agent_id,NEW.position),'present',1,strftime('%Y-%m-%dT%H:%M:%fZ','now'),strftime('%Y-%m-%dT%H:%M:%fZ','now')) ON CONFLICT(source_type,source_id) DO UPDATE SET state='present',episode=attention_operation_epochs.episode+1,first_detected_at=excluded.first_detected_at,last_changed_at=excluded.last_changed_at; END;
CREATE TRIGGER attention_authority_agent_policy_bindings_update AFTER UPDATE OF agent_id,position,source,policy_id,mode,pinned_version,audience,governance ON agent_policy_bindings WHEN json_array(OLD.agent_id,OLD.position,OLD.source,OLD.policy_id,OLD.mode,OLD.pinned_version,OLD.audience,OLD.governance) IS NOT json_array(NEW.agent_id,NEW.position,NEW.source,NEW.policy_id,NEW.mode,NEW.pinned_version,NEW.audience,NEW.governance) BEGIN UPDATE attention_operation_epochs SET state='present',episode=episode+1,first_detected_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'),last_changed_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE source_type='authority_agent_policy_bindings' AND source_id=json_array(NEW.agent_id,NEW.position); END;
CREATE TRIGGER attention_authority_agent_policy_bindings_delete AFTER DELETE ON agent_policy_bindings BEGIN UPDATE attention_operation_epochs SET state='deleted',episode=episode+1,first_detected_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'),last_changed_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE source_type='authority_agent_policy_bindings' AND source_id=json_array(OLD.agent_id,OLD.position); END;

INSERT INTO attention_operation_epochs(source_type,source_id,state,episode,first_detected_at,last_changed_at)
SELECT 'authority_policy_versions',json_array(r.policy_id,r.version),'present',1,strftime('%Y-%m-%dT%H:%M:%fZ','now'),strftime('%Y-%m-%dT%H:%M:%fZ','now') FROM policy_versions r;
CREATE TRIGGER attention_authority_policy_versions_insert AFTER INSERT ON policy_versions BEGIN INSERT INTO attention_operation_epochs(source_type,source_id,state,episode,first_detected_at,last_changed_at) VALUES('authority_policy_versions',json_array(NEW.policy_id,NEW.version),'present',1,strftime('%Y-%m-%dT%H:%M:%fZ','now'),strftime('%Y-%m-%dT%H:%M:%fZ','now')) ON CONFLICT(source_type,source_id) DO UPDATE SET state='present',episode=attention_operation_epochs.episode+1,first_detected_at=excluded.first_detected_at,last_changed_at=excluded.last_changed_at; END;
CREATE TRIGGER attention_authority_policy_versions_update AFTER UPDATE OF policy_id,version,audience,governance,published_at ON policy_versions WHEN json_array(OLD.policy_id,OLD.version,OLD.audience,OLD.governance,OLD.published_at) IS NOT json_array(NEW.policy_id,NEW.version,NEW.audience,NEW.governance,NEW.published_at) BEGIN UPDATE attention_operation_epochs SET state='present',episode=episode+1,first_detected_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'),last_changed_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE source_type='authority_policy_versions' AND source_id=json_array(NEW.policy_id,NEW.version); END;
CREATE TRIGGER attention_authority_policy_versions_delete AFTER DELETE ON policy_versions BEGIN UPDATE attention_operation_epochs SET state='deleted',episode=episode+1,first_detected_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'),last_changed_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE source_type='authority_policy_versions' AND source_id=json_array(OLD.policy_id,OLD.version); END;

-- Terminal result episode anchors.

INSERT INTO attention_operation_epochs(source_type,source_id,state,episode,first_detected_at,last_changed_at)
SELECT 'handoff_result',json_array(handoff_id,claim_epoch),'result',1,recorded_at,recorded_at
FROM (SELECT handoff_id,claim_epoch,COALESCE(updated_at,created_at) AS recorded_at FROM handoffs WHERE status IN ('COMPLETED','REJECTED')) WHERE 1
ON CONFLICT(source_type,source_id) DO UPDATE SET
first_detected_at=CASE WHEN julianday(excluded.first_detected_at)<julianday(attention_operation_epochs.first_detected_at)
    THEN excluded.first_detected_at ELSE attention_operation_epochs.first_detected_at END,
last_changed_at=CASE WHEN julianday(excluded.last_changed_at)>julianday(attention_operation_epochs.last_changed_at)
    THEN excluded.last_changed_at ELSE attention_operation_epochs.last_changed_at END;

INSERT INTO attention_operation_epochs(source_type,source_id,state,episode,first_detected_at,last_changed_at)
SELECT 'handoff_result',json_array(handoff_id,claim_epoch),'result',1,recorded_at,recorded_at
FROM (SELECT handoff_id,claim_epoch,captured_at AS recorded_at FROM (
SELECT r.server_id,r.executor_id,r.operation_id,r.session_id,r.stream_epoch,
       r.terminal_sequence,r.delivery_outcome,r.captured_at,
       p.workspace_id,p.subject_agent_id AS agent_id,b.handoff_id,b.claim_epoch
FROM execution_results r JOIN execution_operations p USING(server_id,executor_id,operation_id)
JOIN execution_domain_deliveries m USING(server_id,executor_id,operation_id)
JOIN delivery_outbox d ON d.operation_id=m.domain_operation_id
JOIN runtime_handoff_bindings b ON b.operation_id=d.operation_id
JOIN handoffs h ON h.handoff_id=b.handoff_id
WHERE r.terminal_sequence IS NOT NULL AND r.delivery_outcome IN ('success','failed','interrupted')
  AND p.action IN ('turn.submit','turn.steer')
  AND p.workspace_id=d.workspace_id AND h.workspace_id=d.workspace_id
  AND p.subject_agent_id=d.recipient_agent_id
  AND (h.claim_epoch<>b.claim_epoch OR h.claimed_by=d.recipient_agent_id)
)) WHERE 1
ON CONFLICT(source_type,source_id) DO UPDATE SET
first_detected_at=CASE WHEN julianday(excluded.first_detected_at)<julianday(attention_operation_epochs.first_detected_at)
    THEN excluded.first_detected_at ELSE attention_operation_epochs.first_detected_at END,
last_changed_at=CASE WHEN julianday(excluded.last_changed_at)>julianday(attention_operation_epochs.last_changed_at)
    THEN excluded.last_changed_at ELSE attention_operation_epochs.last_changed_at END;

CREATE TRIGGER attention_handoff_result_insert AFTER INSERT ON handoffs
WHEN NEW.status IN ('COMPLETED','REJECTED') BEGIN

INSERT INTO attention_operation_epochs(source_type,source_id,state,episode,first_detected_at,last_changed_at)
SELECT 'handoff_result',json_array(handoff_id,claim_epoch),'result',1,recorded_at,recorded_at
FROM (SELECT handoff_id,claim_epoch,COALESCE(updated_at,created_at) AS recorded_at FROM handoffs WHERE status IN ('COMPLETED','REJECTED') AND handoff_id=NEW.handoff_id) WHERE 1
ON CONFLICT(source_type,source_id) DO UPDATE SET
first_detected_at=CASE WHEN julianday(excluded.first_detected_at)<julianday(attention_operation_epochs.first_detected_at)
    THEN excluded.first_detected_at ELSE attention_operation_epochs.first_detected_at END,
last_changed_at=CASE WHEN julianday(excluded.last_changed_at)>julianday(attention_operation_epochs.last_changed_at)
    THEN excluded.last_changed_at ELSE attention_operation_epochs.last_changed_at END;
END;
CREATE TRIGGER attention_handoff_result_terminal AFTER UPDATE OF status,claim_epoch ON handoffs
WHEN NEW.status IN ('COMPLETED','REJECTED') AND (OLD.status IS NOT NEW.status OR OLD.claim_epoch IS NOT NEW.claim_epoch) BEGIN

INSERT INTO attention_operation_epochs(source_type,source_id,state,episode,first_detected_at,last_changed_at)
SELECT 'handoff_result',json_array(handoff_id,claim_epoch),'result',1,recorded_at,recorded_at
FROM (SELECT handoff_id,claim_epoch,COALESCE(updated_at,created_at) AS recorded_at FROM handoffs WHERE status IN ('COMPLETED','REJECTED') AND handoff_id=NEW.handoff_id) WHERE 1
ON CONFLICT(source_type,source_id) DO UPDATE SET
first_detected_at=CASE WHEN julianday(excluded.first_detected_at)<julianday(attention_operation_epochs.first_detected_at)
    THEN excluded.first_detected_at ELSE attention_operation_epochs.first_detected_at END,
last_changed_at=CASE WHEN julianday(excluded.last_changed_at)>julianday(attention_operation_epochs.last_changed_at)
    THEN excluded.last_changed_at ELSE attention_operation_epochs.last_changed_at END;
END;
CREATE TRIGGER attention_execution_result_insert AFTER INSERT ON execution_results
WHEN NEW.terminal_sequence IS NOT NULL BEGIN

INSERT INTO attention_operation_epochs(source_type,source_id,state,episode,first_detected_at,last_changed_at)
SELECT 'handoff_result',json_array(handoff_id,claim_epoch),'result',1,recorded_at,recorded_at
FROM (SELECT handoff_id,claim_epoch,captured_at AS recorded_at FROM (
SELECT r.server_id,r.executor_id,r.operation_id,r.session_id,r.stream_epoch,
       r.terminal_sequence,r.delivery_outcome,r.captured_at,
       p.workspace_id,p.subject_agent_id AS agent_id,b.handoff_id,b.claim_epoch
FROM execution_results r JOIN execution_operations p USING(server_id,executor_id,operation_id)
JOIN execution_domain_deliveries m USING(server_id,executor_id,operation_id)
JOIN delivery_outbox d ON d.operation_id=m.domain_operation_id
JOIN runtime_handoff_bindings b ON b.operation_id=d.operation_id
JOIN handoffs h ON h.handoff_id=b.handoff_id
WHERE r.terminal_sequence IS NOT NULL AND r.delivery_outcome IN ('success','failed','interrupted')
  AND p.action IN ('turn.submit','turn.steer')
  AND p.workspace_id=d.workspace_id AND h.workspace_id=d.workspace_id
  AND p.subject_agent_id=d.recipient_agent_id
  AND (h.claim_epoch<>b.claim_epoch OR h.claimed_by=d.recipient_agent_id)
) WHERE server_id=NEW.server_id AND executor_id=NEW.executor_id AND operation_id=NEW.operation_id) WHERE 1
ON CONFLICT(source_type,source_id) DO UPDATE SET
first_detected_at=CASE WHEN julianday(excluded.first_detected_at)<julianday(attention_operation_epochs.first_detected_at)
    THEN excluded.first_detected_at ELSE attention_operation_epochs.first_detected_at END,
last_changed_at=CASE WHEN julianday(excluded.last_changed_at)>julianday(attention_operation_epochs.last_changed_at)
    THEN excluded.last_changed_at ELSE attention_operation_epochs.last_changed_at END;
END;
CREATE TRIGGER attention_execution_result_terminal AFTER UPDATE OF terminal_sequence,delivery_outcome ON execution_results
WHEN NEW.terminal_sequence IS NOT NULL AND (OLD.terminal_sequence IS NOT NEW.terminal_sequence OR OLD.delivery_outcome IS NOT NEW.delivery_outcome) BEGIN

INSERT INTO attention_operation_epochs(source_type,source_id,state,episode,first_detected_at,last_changed_at)
SELECT 'handoff_result',json_array(handoff_id,claim_epoch),'result',1,recorded_at,recorded_at
FROM (SELECT handoff_id,claim_epoch,captured_at AS recorded_at FROM (
SELECT r.server_id,r.executor_id,r.operation_id,r.session_id,r.stream_epoch,
       r.terminal_sequence,r.delivery_outcome,r.captured_at,
       p.workspace_id,p.subject_agent_id AS agent_id,b.handoff_id,b.claim_epoch
FROM execution_results r JOIN execution_operations p USING(server_id,executor_id,operation_id)
JOIN execution_domain_deliveries m USING(server_id,executor_id,operation_id)
JOIN delivery_outbox d ON d.operation_id=m.domain_operation_id
JOIN runtime_handoff_bindings b ON b.operation_id=d.operation_id
JOIN handoffs h ON h.handoff_id=b.handoff_id
WHERE r.terminal_sequence IS NOT NULL AND r.delivery_outcome IN ('success','failed','interrupted')
  AND p.action IN ('turn.submit','turn.steer')
  AND p.workspace_id=d.workspace_id AND h.workspace_id=d.workspace_id
  AND p.subject_agent_id=d.recipient_agent_id
  AND (h.claim_epoch<>b.claim_epoch OR h.claimed_by=d.recipient_agent_id)
) WHERE server_id=NEW.server_id AND executor_id=NEW.executor_id AND operation_id=NEW.operation_id) WHERE 1
ON CONFLICT(source_type,source_id) DO UPDATE SET
first_detected_at=CASE WHEN julianday(excluded.first_detected_at)<julianday(attention_operation_epochs.first_detected_at)
    THEN excluded.first_detected_at ELSE attention_operation_epochs.first_detected_at END,
last_changed_at=CASE WHEN julianday(excluded.last_changed_at)>julianday(attention_operation_epochs.last_changed_at)
    THEN excluded.last_changed_at ELSE attention_operation_epochs.last_changed_at END;
END;
CREATE TRIGGER attention_handoff_result_delete AFTER DELETE ON handoffs BEGIN
DELETE FROM attention_operation_epochs WHERE source_type='handoff_result' AND json_extract(source_id,'$[0]')=OLD.handoff_id;
END;

WITH aliases AS MATERIALIZED (
    SELECT DISTINCT
        nexus_attention_id_v1('result_unseen','execution_result',operation_id,
            json_array(server_id,executor_id,stream_epoch,terminal_sequence)) AS old_id,
        nexus_attention_id_v1('result_unseen','handoff_result',handoff_id,json(claim_epoch)) AS new_id
    FROM (
SELECT r.server_id,r.executor_id,r.operation_id,r.session_id,r.stream_epoch,
       r.terminal_sequence,r.delivery_outcome,r.captured_at,
       p.workspace_id,p.subject_agent_id AS agent_id,b.handoff_id,b.claim_epoch
FROM execution_results r JOIN execution_operations p USING(server_id,executor_id,operation_id)
JOIN execution_domain_deliveries m USING(server_id,executor_id,operation_id)
JOIN delivery_outbox d ON d.operation_id=m.domain_operation_id
JOIN runtime_handoff_bindings b ON b.operation_id=d.operation_id
JOIN handoffs h ON h.handoff_id=b.handoff_id
WHERE r.terminal_sequence IS NOT NULL AND r.delivery_outcome IN ('success','failed','interrupted')
  AND p.action IN ('turn.submit','turn.steer')
  AND p.workspace_id=d.workspace_id AND h.workspace_id=d.workspace_id
  AND p.subject_agent_id=d.recipient_agent_id
  AND (h.claim_epoch<>b.claim_epoch OR h.claimed_by=d.recipient_agent_id)
)
), legacy AS MATERIALIZED (
    SELECT p.*,a.new_id FROM aliases a JOIN attention_preferences p ON p.attention_id=a.old_id
), candidates AS MATERIALIZED (
    SELECT * FROM legacy UNION ALL
    SELECT p.*,p.attention_id AS new_id FROM attention_preferences p
    WHERE EXISTS(SELECT 1 FROM legacy l WHERE l.principal=p.principal AND l.new_id=p.attention_id)
), merged AS (
    SELECT principal,new_id,
        FIRST_VALUE(seen_at) OVER (PARTITION BY principal,new_id
            ORDER BY seen_at IS NULL,nexus_attention_stamp_v1(seen_at),seen_at) AS seen_at,
        FIRST_VALUE(snoozed_until) OVER (PARTITION BY principal,new_id
            ORDER BY nexus_attention_stamp_v1(snoozed_until) DESC,snoozed_until DESC) AS snoozed_until,
        FIRST_VALUE(updated_at) OVER (PARTITION BY principal,new_id
            ORDER BY nexus_attention_stamp_v1(updated_at) DESC,updated_at DESC) AS updated_at,
        MAX(revision) OVER (PARTITION BY principal,new_id)+1 AS revision,
        ROW_NUMBER() OVER (PARTITION BY principal,new_id ORDER BY attention_id) AS ordinal
    FROM candidates
)
INSERT INTO attention_preferences(principal,attention_id,seen_at,snoozed_until,revision,updated_at)
SELECT principal,new_id,seen_at,snoozed_until,revision,updated_at FROM merged WHERE ordinal=1
ON CONFLICT(principal,attention_id) DO UPDATE SET seen_at=excluded.seen_at,
    snoozed_until=excluded.snoozed_until,revision=excluded.revision,updated_at=excluded.updated_at;
