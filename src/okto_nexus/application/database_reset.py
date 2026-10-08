"""Separate connection configuration from resettable operational history."""

# These are installation invariants, not execution history. Migration seeds
# are not re-run when schema_migrations is preserved by a database reset.
INSTALLATION_TABLES = frozenset({
    'schema_migrations', 'settings', 'execution_installation',
    'runtime_policy_defaults', 'runtime_artifact_settings',
    'runtime_writer_contract', 'runtime_dispatcher_owner', 'runtime_journal_checkpoint',
    'runtime_reset_generation',
})

# Preserve the whole configured connection, including its original authority
# and spent quota. A reset must not broaden or renew any permission.
AGENT_CONFIGURATION_TABLES = frozenset({
    'agents', 'agent_endpoints', 'runtime_profiles', 'runtime_execution_grants',
    'agent_connection_policies', 'agent_connection_methods', 'agent_connection_keys',
    'agent_execution_policies', 'agent_runtime_overrides', 'agent_runtime_policy_epochs',
    'runtime_boot_bindings', 'execution_agent_revisions', 'execution_executors',
    'execution_bindings', 'execution_workspace_bindings', 'execution_realizations',
    'execution_local_realizations', 'execution_local_observations',
    'execution_inventory_snapshots', 'execution_inventory_current',
    'execution_inventory_revalidation', 'execution_proposals', 'connection_setup_commits',
    'execution_link_tickets', 'execution_control_lanes', 'execution_connection_resumes',
    'workspaces', 'permission_presets', 'tag_keys', 'tag_values',
    'agent_policy_bindings', 'policies', 'policy_versions', 'governance_policies',
    'agent_comm_binding', 'comm_presets', 'comm_preset_versions',
    'agent_groups', 'agent_group_members', 'guardrails', 'guardrail_versions', 'guardrail_assignments',
})


def preserved_tables(conn, *, keep_agents):
    tables = {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
    preserved = set(INSTALLATION_TABLES)
    if keep_agents:
        preserved.update(AGENT_CONFIGURATION_TABLES)
    preserved &= tables
    # Preserve dependencies too, so adding a required FK to a configuration
    # table cannot silently erase part of an existing connection on upgrade.
    pending = list(preserved)
    while pending:
        table = pending.pop()
        escaped = table.replace('"', '""')
        for row in conn.execute(f'PRAGMA foreign_key_list("{escaped}")'):
            dependency = row[2]
            if dependency in tables and dependency not in preserved:
                preserved.add(dependency)
                pending.append(dependency)
    return preserved


def clear_operational_history(conn, *, keep_agents):
    """Clear history in the drained reset's existing writer transaction.

    Attempt events remain immutable for normal writers. Only this explicit
    operator reset suspends their delete trigger, transactionally: concurrent
    writers cannot observe the gap, and rollback restores the original schema.
    Other writer/authority fences remain active throughout the reset.
    """
    preserved = preserved_tables(conn, keep_agents=keep_agents)
    trigger = conn.execute("SELECT sql FROM sqlite_master WHERE type='trigger' "
        "AND name='runtime_delivery_attempt_no_delete' "
        "AND tbl_name='runtime_delivery_attempt_events'").fetchone()
    if trigger is not None:
        conn.execute('DROP TRIGGER runtime_delivery_attempt_no_delete')
    conn.execute('PRAGMA defer_foreign_keys=ON')
    tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%'").fetchall()
    counts = {}
    for row in tables:
        table = row[0]
        if table not in preserved:
            escaped = table.replace('"', '""')
            counts[table] = conn.execute(f'DELETE FROM "{escaped}"').rowcount
    if trigger is not None:
        conn.execute(trigger[0])
    conn.execute('UPDATE runtime_reset_generation SET generation=generation+1 WHERE singleton=1')
    return counts
