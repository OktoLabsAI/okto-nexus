def seed_board(s, identities):
    """Synthetic retained SQLite facts, not a producer or native success claim."""
    with s.factory.unit_of_work() as uow:
        c, now = uow.connection, s.clock.now_iso()
        copy = base.fixtures._copy
        endpoint = c.execute("SELECT * FROM agent_endpoints WHERE endpoint_id='ui-ep-2'").fetchone()
        binding = c.execute("SELECT * FROM execution_bindings WHERE binding_id='ui-binding-2'").fetchone()
        unknown = c.execute("SELECT * FROM execution_operations WHERE operation_id='ui-unknown'").fetchone()
        unknown_receipt = c.execute("SELECT * FROM execution_receipts WHERE operation_id='ui-unknown'").fetchone()
        operation = c.execute("SELECT * FROM execution_operations WHERE operation_id='ui-success'").fetchone()
        receipt = c.execute("SELECT * FROM execution_receipts WHERE operation_id='ui-success'").fetchone()
        result = c.execute("SELECT * FROM execution_results WHERE operation_id='ui-success'").fetchone()
        # The base historical CLOSED session's synthetic containment request is
        # deliberately absent in this separate completed-history scenario.
        c.execute("DELETE FROM execution_session_containment WHERE session_id='ui-session-2'")
        for i in range(12):
            ep, bid, oid = f'board-idle-ep-{i:02}', f'board-idle-binding-{i:02}', f'board-result-{i:02}'
            copy(c, 'agent_endpoints', endpoint, endpoint_id=ep)
            copy(c, 'execution_bindings', binding, binding_id=bid, endpoint_id=ep)
            copy(c, 'execution_operations', unknown, operation_id=f'board-unknown-{i:02}')
            copy(c, 'execution_receipts', unknown_receipt, operation_id=f'board-unknown-{i:02}', received_at=now)
            copy(c, 'execution_operations', operation, operation_id=oid)
            copy(c, 'execution_receipts', receipt, operation_id=oid, received_at=now)
            c.execute("INSERT INTO execution_event_ingress VALUES(?,?,'ui-session-2','ui-historical-epoch',?,?, 'turn.completed','{}',?)", (result['server_id'], result['executor_id'], 100+i, f'board-event-{i:02}', now))
            copy(c, 'execution_results', result, operation_id=oid, terminal_sequence=100+i, output_text=f'Synthetic retained result {i:02}', captured_at=now)
        identities['board_seed'] = {'idle_bindings':12,'retained_unknown_operations':12,'historical_results':12,'historical_containment_absent':True,'native_execution_claim':False}
