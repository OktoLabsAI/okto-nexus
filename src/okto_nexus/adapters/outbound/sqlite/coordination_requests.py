"""Minimal coordination receipts within the caller's canonical transaction.

No method opens/commits a connection or authorizes a caller. The application
must revalidate identity and visibility before reading; creation must look up
the intent before effects, then record the reference in that SAME write UoW.
The immutable key includes the persisted Server installation, never a client
supplied installation ID. Resource deletion leaves a tombstone until expiry.
"""
from __future__ import annotations

from functools import wraps
import sqlite3

from ....domain.base import iso_plus
from ....domain.coordination_requests import (
    RETENTION_SECONDS, CoordinationReceipt, CoordinationRequestKey, conflict, validate_hash,
)
from ....errors import ErrorCode, OktoNexusError, db_error_from_exception


_WHERE = "server_id=? AND actor_agent_id=? AND workspace_id=? AND operation=? AND client_request_id=?"


def _database_errors(fn):
    @wraps(fn)
    def run(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except sqlite3.Error as exc:
            raise db_error_from_exception("accessing coordination receipts", exc) from exc
    return run


class SqliteCoordinationRequestRepo:
    @_database_errors
    def key(self, uow, *, actor_agent_id, workspace_id, operation, client_request_id):
        row = uow.connection.execute(
            "SELECT server_id FROM execution_installation WHERE singleton=1").fetchone()
        if row is None:
            raise OktoNexusError(ErrorCode.INTERNAL_ERROR, "Server installation identity is unavailable.", {})
        return CoordinationRequestKey(row["server_id"], actor_agent_id, workspace_id, operation, client_request_id)

    @staticmethod
    def _write(uow, key=None):
        if not uow.connection.in_transaction or not getattr(uow, "_write", False):
            raise OktoNexusError(ErrorCode.INTERNAL_ERROR,
                "A coordination receipt requires the canonical write unit of work.", {})
        if key is not None:
            installation = uow.connection.execute(
                "SELECT server_id FROM execution_installation WHERE singleton=1").fetchone()
            if installation is None or installation["server_id"] != key.server_id:
                raise conflict("CLIENT_REQUEST_INSTALLATION_CONFLICT")

    @_database_errors
    def get(self, uow, key: CoordinationRequestKey) -> CoordinationReceipt | None:
        row = uow.connection.execute("SELECT * FROM coordination_requests WHERE " + _WHERE, key.values()).fetchone()
        if row is None:
            return None
        return CoordinationReceipt(key, row["request_hash"], row["state"], row["resource_id"],
                                   row["approval_id"], row["created_at"], row["expires_at"])

    def lookup(self, uow, key, *, request_hash, now):
        validate_hash(request_hash)
        iso_plus(now, 0)
        receipt = self.get(uow, key)
        if receipt is not None:
            receipt.require_replay(request_hash=request_hash, now=now)
        return receipt

    @staticmethod
    def _resource(uow, key, resource_id):
        # Table and column names come only from the fixed operation vocabulary.
        table, column = ("messages", "message_id") if key.operation == "message_create" else ("handoffs", "handoff_id")
        row = uow.connection.execute(
            f"SELECT workspace_id,from_agent_id FROM {table} WHERE {column}=?", (resource_id,)).fetchone()
        if row is not None and (row["workspace_id"] != key.workspace_id or row["from_agent_id"] != key.actor_agent_id):
            raise conflict("CLIENT_REQUEST_RESOURCE_SCOPE_CONFLICT")
        return row

    @staticmethod
    def _approval(uow, key, approval_id):
        row = uow.connection.execute("SELECT workspace_id,agent_id,action,status,archived_at FROM approvals WHERE approval_id=?",
                                     (approval_id,)).fetchone()
        actions = ("message_create", "broadcast") if key.operation == "message_create" else ("handoff_create",)
        if row is not None and (row["workspace_id"] != key.workspace_id or row["agent_id"] != key.actor_agent_id
                                or row["action"] not in actions):
            raise conflict("CLIENT_REQUEST_APPROVAL_SCOPE_CONFLICT")
        return row

    @_database_errors
    def record(self, uow, key, *, request_hash, now, resource_id=None, approval_id=None):
        """Record exactly one creation OR pending approval; never overwrite one.

        Re-recording a different object fails, rolling back accidental duplicate
        canonical effects with the caller's UoW. Approval execution must use
        resolve_approval, which preserves the original deadline and correlation.
        """
        self._write(uow, key)
        if (resource_id is None) == (approval_id is None):
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Record one resource or pending approval.", {})
        old = self.lookup(uow, key, request_hash=request_hash, now=now)
        state = "created" if resource_id is not None else "pending_approval"
        if old is not None:
            if (old.state, old.resource_id, old.approval_id) != (state, resource_id, approval_id):
                raise conflict("CLIENT_REQUEST_REFERENCE_CONFLICT")
            return old
        if resource_id is not None:
            if self._resource(uow, key, resource_id) is None:
                raise conflict("CLIENT_REQUEST_RESOURCE_MISSING")
        else:
            approval = self._approval(uow, key, approval_id)
            if approval is None or approval["status"] != "pending" or approval["archived_at"]:
                raise conflict("CLIENT_REQUEST_APPROVAL_NOT_PENDING")
        expires_at = iso_plus(now, RETENTION_SECONDS)
        uow.connection.execute("INSERT INTO coordination_requests VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (*key.values(), request_hash, state, resource_id, approval_id, now, expires_at))
        return self.get(uow, key)

    @_database_errors
    def resolve_approval(self, uow, key, *, request_hash, approval_id, resource_id, now):
        """Advance the SAME receipt with the object created by approved replay.

        The caller must additionally validate the persisted original authority
        and finalize the approval result/event in this transaction. This method
        does not grant authority or bypass any creation/approval policy.
        """
        self._write(uow, key)
        old = self.lookup(uow, key, request_hash=request_hash, now=now)
        if old is None or old.approval_id != approval_id:
            raise conflict("CLIENT_REQUEST_APPROVAL_REFERENCE_MISSING")
        if old.state == "created":
            if old.resource_id != resource_id:
                raise conflict("CLIENT_REQUEST_REFERENCE_CONFLICT")
            return old
        approval = self._approval(uow, key, approval_id)
        if approval is None or approval["status"] != "approved" or approval["archived_at"]:
            raise conflict("CLIENT_REQUEST_APPROVAL_NOT_APPROVED")
        if resource_id is None or self._resource(uow, key, resource_id) is None:
            raise conflict("CLIENT_REQUEST_RESOURCE_MISSING")
        uow.connection.execute("UPDATE coordination_requests SET state='created',resource_id=? WHERE " + _WHERE,
                               (resource_id, *key.values()))
        return self.get(uow, key)

    @_database_errors
    def reference(self, uow, receipt, *, now):
        """Read metadata/tombstones without replaying or touching presence.

        A created receipt only proves canonical creation. It never proves
        delivery, execution or handoff completion. Resource reads remain gated
        by their own current access rules in the application.
        """
        iso_plus(now, 0)
        result = receipt.reference()
        if now < receipt.created_at or now >= receipt.expires_at:
            result["state"] = "expired"
        elif receipt.state == "created":
            if self._resource(uow, receipt.key, receipt.resource_id) is None:
                result["state"] = "resource_removed"
        else:
            approval = self._approval(uow, receipt.key, receipt.approval_id)
            result["state"] = ("approval_removed" if approval is None else
                "approval_archived" if approval["archived_at"] else
                {"pending": "pending_approval", "approved": "approved_awaiting_execution",
                 "rejected": "rejected"}[approval["status"]])
        return result

    @staticmethod
    @_database_errors
    def count_expired(uow, *, cutoff):
        iso_plus(cutoff, 0)
        return uow.connection.execute("SELECT COUNT(*) FROM coordination_requests WHERE expires_at<=?", (cutoff,)).fetchone()[0]

    @_database_errors
    def prune_expired(self, uow, *, cutoff, limit):
        self._write(uow)
        iso_plus(cutoff, 0)
        if type(limit) is not int or limit < 1:
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "A positive prune batch limit is required.", {})
        return uow.connection.execute("DELETE FROM coordination_requests WHERE rowid IN "
            "(SELECT rowid FROM coordination_requests WHERE expires_at<=? ORDER BY expires_at,rowid LIMIT ?)",
            (cutoff, limit)).rowcount
