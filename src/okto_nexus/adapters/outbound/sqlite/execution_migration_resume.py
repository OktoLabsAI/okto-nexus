"""Verify preserved backup rows across explicitly receipted endpoint adoption."""
import json
from pathlib import Path
import sqlite3

from .execution_legacy_migration import SOURCE, _row_digest
from .migration_backup import _quoted


def require_adopted_baseline(conn, manifest):
    adopted = {}
    for record in conn.execute("SELECT * FROM execution_migration_map WHERE source=? "
                               "AND source_type='agent_endpoints' AND state='BINDING_ADOPTED'", (SOURCE,)):
        ref = json.loads(record["canonical_ref"])
        receipt = ref.get("adoption")
        fields = {"proposal_id", "endpoint_digest", "profile_id", "profile_digest", "binding_id", "binding_digest"}
        if not isinstance(receipt, dict) or set(receipt) != fields:
            raise ValueError("The adopted endpoint has no verifiable migration receipt.")
        for table, field, key, digest in (
                ("agent_endpoints","endpoint_id",record["legacy_id"],receipt["endpoint_digest"]),
                ("runtime_profiles","profile_id",receipt["profile_id"],receipt["profile_digest"]),
                ("execution_bindings","binding_id",receipt["binding_id"],receipt["binding_digest"])):
            if key is None and table == "runtime_profiles":
                continue
            row = conn.execute("SELECT * FROM "+table+" WHERE "+field+"=?", (key,)).fetchone()
            if row is None or _row_digest(row) != digest:
                raise ValueError("An adopted migration resource changed; review is required.")
        adopted[record["legacy_id"]] = (record["row_digest_before"],
            ref.get("backup_source_columns"), ref.get("backup_source_digest"))

    original = sqlite3.connect(Path(manifest["_backup_database"]).as_uri()+"?mode=ro",uri=True)
    original.row_factory = sqlite3.Row
    try:
        for table, expected in manifest["inventory"]["tables"].items():
            if table == "runtime_dispatcher_owner":
                continue  # The caller independently requires no live owner.
            info = original.execute("PRAGMA table_info("+_quoted(table)+")").fetchall()
            primary = [row[1] for row in sorted(info,key=lambda item:item[5]) if row[5]]
            columns = expected["columns"]
            for before in original.execute("SELECT * FROM "+_quoted(table)):
                if table == "agent_endpoints" and before["endpoint_id"] in adopted:
                    full_digest, source_columns, source_digest = adopted[before["endpoint_id"]]
                    if source_columns is not None and source_columns != columns:
                        raise ValueError("The adopted endpoint backup columns changed.")
                    expected_digest = source_digest if source_columns is not None else full_digest
                    if _row_digest(before) != expected_digest:
                        raise ValueError("The adopted endpoint does not match the original backup.")
                    continue
                keys = primary or columns
                where = " AND ".join(_quoted(key)+" IS ?" for key in keys)
                current = conn.execute("SELECT "+",".join(_quoted(key) for key in columns)+
                    " FROM "+_quoted(table)+" WHERE "+where,tuple(before[key] for key in keys)).fetchone()
                if not primary:
                    count_sql = "SELECT COUNT(*) FROM "+_quoted(table)+" WHERE "+where
                    values = tuple(before[key] for key in keys)
                    if conn.execute(count_sql,values).fetchone()[0] < original.execute(count_sql,values).fetchone()[0]:
                        raise ValueError("Preserved migration source rows disappeared.")
                volatile = {"last_seen_at"} if table in {"agents","workspaces"} else set()
                if table == "execution_executors":
                    volatile = {"control_state","generation","owner_instance_id","last_seen_at"}
                if table == "runtime_writer_contract":
                    # Starting serve installs its writer fence. Owner liveness
                    # is checked separately before this offline comparison.
                    volatile = {"owner_id", "owner_epoch", "admission_enabled"}
                    if current is not None and before["required_contract"] == 0 and current["required_contract"] == 1:
                        volatile.add("required_contract")
                if current is None or any(current[key] != before[key] for key in columns if key not in volatile):
                    raise ValueError(f"A preserved migration source row changed or disappeared in {table}.")
    finally:
        original.close()
