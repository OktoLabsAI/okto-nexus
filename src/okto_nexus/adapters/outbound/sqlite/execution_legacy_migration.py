"""Explicit, resumable legacy catalog translation; never an execution registry."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import secrets
import sqlite3

from .migration_backup import _encoded, _quoted
from .execution_identity import ensure_execution_installation

# This closed map is migration-only. Historical rows/hashes remain untouched.
LEGACY_ADAPTERS = {
    "codex": "codex_app_server",
    "pi": "pi_rpc",
    "claude_code.stream": "claude_stream",
    "claude_code.attach": "claude_attach",
}
SOURCE = "nexus-r4-catalog-v1"
TABLES = (("runtime_profiles", "profile_id"), ("agent_endpoints", "endpoint_id"))


def load_backup_manifest(directory):
    directory = Path(directory).resolve()
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("format") != "nexus-migration-backup-v1" or manifest.get("database") != "nexus.db":
        raise ValueError("The migration requires a Nexus migration backup.")
    digest = hashlib.sha256()
    with (directory / "nexus.db").open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    if digest.hexdigest() != manifest["database_sha256"]:
        raise ValueError("The migration backup digest does not match its database.")
    # Validate the inventory against the actual immutable backup as well.
    from .migration_backup import snapshot_inventory
    connection = sqlite3.connect((directory / "nexus.db").as_uri()+"?mode=ro", uri=True)
    try:
        if snapshot_inventory(connection) != manifest["inventory"]:
            raise ValueError("The migration backup inventory does not match its database.")
    finally:
        connection.close()
    manifest["_backup_database"] = str(directory / "nexus.db")
    return manifest


def require_preserved_baseline(conn, manifest):
    """Compare old columns, allowing additive R4 columns/tables after expansion."""
    if conn.execute("SELECT 1 FROM sqlite_master WHERE name='execution_migration_map'").fetchone():
        if conn.execute("SELECT 1 FROM execution_migration_map WHERE source=? AND state='BINDING_ADOPTED' LIMIT 1",
                        (SOURCE,)).fetchone():
            from .execution_migration_resume import require_adopted_baseline
            return require_adopted_baseline(conn, manifest)
    for table, expected in manifest["inventory"]["tables"].items():
        columns = expected["columns"]
        digest, count = hashlib.sha256(), 0
        selection = ",".join(_quoted(name) for name in columns)
        restriction = ""
        if table == "agent_connection_methods" and conn.execute(
                "SELECT 1 FROM sqlite_master WHERE name='execution_migration_map'").fetchone():
            restriction = (" WHERE NOT EXISTS (SELECT 1 FROM execution_migration_map m "
                "WHERE m.source='nexus-r4-catalog-v1' AND m.source_type='agent_connection_methods' "
                "AND json_extract(m.canonical_ref,'$.created_canonical_denial')=1 "
                "AND json_extract(m.canonical_ref,'$.agent_id')=agent_connection_methods.agent_id "
                "AND json_extract(m.canonical_ref,'$.canonical_method')=agent_connection_methods.method)")
        for row in conn.execute("SELECT "+selection+" FROM "+_quoted(table)+restriction+" ORDER BY "+selection):
            encoded = _encoded(tuple(row))
            digest.update(len(encoded).to_bytes(8, "big"))
            digest.update(encoded)
            count += 1
        if count != expected["rows"] or digest.hexdigest() != expected["sha256"]:
            raise ValueError("The database changed since its migration backup.")


def _backfill_catalog_batch(factory, manifest, *, batch_size=100):
    if isinstance(batch_size, bool) or not isinstance(batch_size, int) or not 1 <= batch_size <= 1000:
        raise ValueError("The migration batch size must be between 1 and 1000.")
    installation = ensure_execution_installation(factory)
    baseline = migration_baseline(manifest)
    batch_id = "migration_" + secrets.token_hex(16)
    processed = 0
    with factory.unit_of_work() as uow:
        conn = uow.connection
        require_idle_migration_owner(conn)
        require_preserved_baseline(conn, baseline)
        processed = _backfill_method_denials(conn, batch_id, batch_size)
        for table, key in TABLES:
            # Detect drift in a previously recorded row instead of silently
            # assigning the same ID to a different migration source.
            for old in conn.execute("SELECT legacy_id,row_digest_before,state FROM execution_migration_map "
                                    "WHERE source=? AND source_type=?", (SOURCE, table)):
                if old["state"] == "BINDING_ADOPTED":
                    continue  # The preserved-baseline check validated the adoption receipt.
                row = conn.execute("SELECT * FROM "+table+" WHERE "+key+"=?", (old[0],)).fetchone()
                if row is None or _row_digest(row) != old[1]:
                    raise ValueError("A previously migrated source row changed; review is required.")
            generated = _generated_profile_filter(table)
            rows = conn.execute("SELECT t.* FROM "+table+" t WHERE "+generated+"NOT EXISTS "
                "(SELECT 1 FROM execution_migration_map m WHERE m.source=? AND m.source_type=? "
                "AND m.legacy_id=t."+key+") ORDER BY t."+key+" LIMIT ?",
                (SOURCE, table, batch_size-processed)).fetchall()
            for row in rows:
                adapter = LEGACY_ADAPTERS.get(row["adapter_id"])
                state = ("TOOLS_ONLY" if row["adapter_id"] == "mcp" else
                         "REDISCOVERY_REQUIRED" if adapter else "MIGRATION_REVIEW_REQUIRED")
                reference = {"legacy_id": row[key], "canonical_adapter_id": adapter,
                    "server_id": installation.server_id,
                    "executor_id": installation.embedded_executor_id if adapter else None,
                    "consent_required": bool(adapter)}
                if table == "agent_endpoints":
                    # The backup may predate additive schema columns. Retain a
                    # separate digest in its original column space for resume.
                    columns = baseline["inventory"]["tables"][table]["columns"]
                    reference["backup_source_columns"] = columns
                    reference["backup_source_digest"] = _row_digest({name: row[name] for name in columns})
                    reference.update(agent_id=row["agent_id"], workspace_id=row["workspace_id"],
                                     endpoint_id=row["endpoint_id"])
                    binding = conn.execute("SELECT binding_id,executor_id FROM execution_bindings "
                                           "WHERE endpoint_id=?", (row[key],)).fetchone()
                    if binding is not None:
                        state = "EXISTING_BINDING"
                        reference.update(binding_id=binding[0], executor_id=binding[1], canonical_adapter_id=row["adapter_id"])
                conn.execute("INSERT INTO execution_migration_map(source,source_type,legacy_id,"
                    "canonical_ref,row_digest_before,migration_batch_id,state) VALUES(?,?,?,?,?,?,?)",
                    (SOURCE,table,row[key],json.dumps(reference,sort_keys=True,separators=(",",":")),
                     _row_digest(row),batch_id,state))
                processed += 1
            if processed == batch_size:
                break
        remaining = sum(conn.execute("SELECT COUNT(*) FROM "+table+" t WHERE "+_generated_profile_filter(table)+"NOT EXISTS "
            "(SELECT 1 FROM execution_migration_map m WHERE m.source=? AND m.source_type=? "
            "AND m.legacy_id=t."+key+")", (SOURCE,table)).fetchone()[0] for table,key in TABLES)
    return {"status": "CATALOG_BACKFILL_COMPLETE" if not remaining else "CATALOG_BACKFILL_PENDING",
            "processed": processed, "remaining": remaining,
            "migration_batch_id": batch_id if processed else None,
            "execution_activated": False}


def _row_digest(row):
    return hashlib.sha256(json.dumps(dict(row),sort_keys=True,separators=(",",":"),
                                    ensure_ascii=True).encode()).hexdigest()


def migration_baseline(manifest):
    tables = manifest["inventory"]["tables"]
    return {**manifest, "inventory": {**manifest["inventory"], "tables": {
        name: value for name, value in tables.items()
        if name not in {"schema_migrations", "execution_migration_map"}
        and not (name in {"execution_installation", "execution_executors"} and value["rows"] == 0)}}}


def backfill_catalog_batch(factory, manifest, *, batch_size=100):
    try:
        return _backfill_catalog_batch(factory, manifest, batch_size=batch_size)
    except sqlite3.Error as error:
        raise ValueError("The migration batch could not be committed.") from error


def _pending_methods(conn, limit):
    return conn.execute(
        "SELECT * FROM agent_connection_methods t WHERE t.method IN (?,?,?,?) "
        "AND NOT EXISTS (SELECT 1 FROM execution_migration_map m WHERE m.source=? "
        "AND m.source_type='agent_connection_methods' AND m.legacy_id=json_array(t.agent_id,t.method)) "
        "ORDER BY t.agent_id,t.method LIMIT ?", (*LEGACY_ADAPTERS, SOURCE, limit)).fetchall()


def _backfill_method_denials(conn, batch_id, limit):
    for saved in conn.execute("SELECT * FROM execution_migration_map WHERE source=? "
                              "AND source_type='agent_connection_methods'", (SOURCE,)):
        agent, method = json.loads(saved["legacy_id"])
        source = conn.execute("SELECT * FROM agent_connection_methods WHERE agent_id=? AND method=?",
                              (agent, method)).fetchone()
        if source is None or _row_digest(source) != saved["row_digest_before"]:
            raise ValueError("A migrated connection policy changed; review is required.")
        ref = json.loads(saved["canonical_ref"])
        if ref["denied"]:
            canonical = conn.execute("SELECT enabled FROM agent_connection_methods WHERE agent_id=? AND method=?",
                                     (agent, ref["canonical_method"])).fetchone()
            if canonical is None or canonical[0] != 0:
                raise ValueError("A canonical migration denial changed; review is required.")
    rows = _pending_methods(conn, limit)
    for row in rows:
        canonical = LEGACY_ADAPTERS[row["method"]]
        denied, created = row["enabled"] == 0, False
        if denied:
            current = conn.execute("SELECT enabled FROM agent_connection_methods WHERE agent_id=? AND method=?",
                                   (row["agent_id"], canonical)).fetchone()
            if current is not None and current[0] != 0:
                raise ValueError("Legacy denial conflicts with canonical policy; review is required.")
            if current is None:
                conn.execute("INSERT INTO agent_connection_methods(agent_id,method,enabled) VALUES(?,?,0)",
                             (row["agent_id"], canonical))
                created = True
        ref = {"agent_id": row["agent_id"], "canonical_method": canonical,
               "denied": denied, "created_canonical_denial": created}
        conn.execute("INSERT INTO execution_migration_map(source,source_type,legacy_id,canonical_ref,"
                     "row_digest_before,migration_batch_id,state) VALUES(?,?,?,?,?,?,?)",
                     (SOURCE, "agent_connection_methods", json.dumps([row["agent_id"],row["method"]],separators=(",",":")),
                      json.dumps(ref,sort_keys=True,separators=(",",":")), _row_digest(row), batch_id,
                      "DENIAL_PRESERVED" if denied else "CONSENT_REQUIRED"))
    return len(rows)


def require_idle_migration_owner(conn):
    if conn.execute("SELECT 1 FROM sqlite_master WHERE name='runtime_dispatcher_owner'").fetchone():
        row = conn.execute("SELECT lease_expires_at FROM runtime_dispatcher_owner WHERE owner_key='dispatcher'").fetchone()
        if row:
            expiry = datetime.fromisoformat(row[0].replace("Z", "+00:00"))
            if expiry.tzinfo is None or expiry > datetime.now(timezone.utc):
                raise ValueError("Stop and drain the runtime owner before migrating execution policy.")


def _generated_profile_filter(table):
    if table != "runtime_profiles":
        return ""
    return ("NOT EXISTS (SELECT 1 FROM execution_migration_map a WHERE a.source='nexus-r4-catalog-v1' "
            "AND a.source_type='agent_endpoints' AND a.state='BINDING_ADOPTED' "
            "AND json_extract(a.canonical_ref,'$.adoption.profile_id')=t.profile_id) AND ")
