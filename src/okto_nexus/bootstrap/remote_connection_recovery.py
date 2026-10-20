"""Fence transport owners that cannot survive a Server process restart."""

from ..adapters.outbound.sqlite.execution_identity import ensure_execution_installation


def fence_remote_connections_after_restart(factory) -> int:
    """Discard only socket authority; retain native leases and receipt history.

    A WebSocket and its short resume window belong to the previous Server
    process. Its Connector may still be executing an authorized lease, so this
    transaction neither revokes leases nor discards pending publications.
    """
    server_id = ensure_execution_installation(factory).server_id
    with factory.unit_of_work() as uow:
        conn = uow.connection
        rows = conn.execute(
            "SELECT executor_id FROM execution_executors WHERE server_id=? "
            "AND kind='remote'", (server_id,),
        ).fetchall()
        for row in rows:
            executor_id = row["executor_id"]
            conn.execute(
                "UPDATE execution_executors SET owner_instance_id=NULL,"
                "control_state='DISCONNECTED' WHERE server_id=? AND executor_id=?",
                (server_id, executor_id),
            )
            conn.execute(
                "UPDATE execution_control_lanes SET state='DISCONNECTED' "
                "WHERE server_id=? AND executor_id=?",
                (server_id, executor_id),
            )
            conn.execute(
                "UPDATE execution_link_tickets SET bound_connection_id=NULL "
                "WHERE server_id=? AND executor_id=?",
                (server_id, executor_id),
            )
            conn.execute(
                "DELETE FROM execution_connection_resumes WHERE server_id=? "
                "AND executor_id=?", (server_id, executor_id),
            )
    return len(rows)
