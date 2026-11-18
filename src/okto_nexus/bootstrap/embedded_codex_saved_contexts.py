"""Retain a private history observation across a normal, authorized close."""

import asyncio
import json
import logging
import sqlite3
import time
from dataclasses import asdict
from pathlib import Path

from nexus_connector_core import (
    CodexRolloutEvidence,
    CoreError,
    OperationKey,
    SessionKey,
    project_r4_bound_receipt,
    project_r4_resource_release,
)
from nexus_connector_core.native.codex_rollout import observe_rollout

from ..application.execution_native_session_mapping import reviewed_codex_context
from ..domain.execution.keys import SessionKey as DomainSessionKey
from ..domain.execution.keys import SessionOwnerGeneration
from ..domain.session_interaction import InputScope
from ..errors import ErrorCode, OktoNexusError

_OBSERVATION_TIMEOUT = 5
_LOG = logging.getLogger(__name__)

_READY = """
    SELECT c.*, close.binding_json AS close_binding,
           opening.binding_json AS opening_binding, r.canonical_frame, r.receipt_revision
    FROM embedded_codex_saved_contexts c
    JOIN execution_sessions s USING (server_id, executor_id, session_id)
    JOIN execution_local_publications close
      ON close.server_id=c.server_id AND close.executor_id=c.executor_id
     AND close.operation_id=c.close_operation_id AND close.session_id=c.session_id
    JOIN execution_local_publications opening
      ON opening.server_id=c.server_id AND opening.executor_id=c.executor_id
     AND opening.operation_id=c.opening_operation_id AND opening.session_id=c.session_id
    JOIN execution_receipts r
      ON r.server_id=c.server_id AND r.executor_id=c.executor_id AND r.operation_id=c.close_operation_id
     AND r.receipt_revision=(SELECT MAX(previous.receipt_revision) FROM execution_receipts previous
         WHERE previous.server_id=r.server_id AND previous.executor_id=r.executor_id
           AND previous.operation_id=r.operation_id)
    JOIN execution_operations operation
      ON operation.server_id=c.server_id AND operation.executor_id=c.executor_id
     AND operation.operation_id=c.close_operation_id AND operation.session_id=c.session_id
    WHERE c.server_id=:server_id AND c.executor_id=:executor_id AND c.status='CAPTURED'
      AND c.close_operation_id=:close_id
      AND s.open_operation_id=c.opening_operation_id AND s.owner_generation=c.owner_generation
      AND s.stream_epoch=c.stream_epoch AND s.lifecycle_state='CLOSED' AND s.lease_state='CLOSED'
      AND operation.action='runtime.close' AND r.stage='SUCCEEDED' AND r.possible_effect=1
      AND NOT EXISTS (SELECT 1 FROM embedded_codex_saved_contexts verified
          WHERE verified.server_id=c.server_id AND verified.executor_id=c.executor_id
            AND verified.session_id=c.session_id AND verified.owner_generation=c.owner_generation
            AND verified.status='VERIFIED')
"""


class EmbeddedCodexSavedContexts:
    def __init__(self, owner):
        self.owner = owner
        self._after = 0

    async def capture(self, frame, runtime, workspace_root, *, lease_deadline):
        """Observe while the source is still owned. A missing observation cannot block close."""
        if not self.owner.deps.config.runtime_session_interaction_enabled:
            return
        # Close retains the authority gate during capture. Give the normal
        # close path time to revalidate and enter Core before lease expiry.
        budget = min(_OBSERVATION_TIMEOUT, lease_deadline - time.monotonic() - 1)
        if budget <= 0:
            return
        scope = InputScope(
            DomainSessionKey(frame['server_id'], frame['executor_id'], frame['session_id']),
            SessionOwnerGeneration(frame['session_owner_generation']), frame['binding_id'],
            frame['workspace_id'], frame['workspace_binding_id'], frame['agent_id'])
        try:
            async with asyncio.timeout(budget):
                async with self.owner._native_presentation_context(scope) as (runtime_scope, mapping, target, channel):
                    if not reviewed_codex_context(mapping):
                        return
                    observed = await runtime.read_live_codex_rollout(
                        runtime_scope, target, mapping.codex_thread_id, connection_id=channel.connection_id,
                        connection_generation=channel.connection_generation)
                if observed is None:
                    return
                proof, rollout = observed
                if (proof.key != SessionKey(**asdict(scope.session)) or proof.target != target
                        or proof.owner_generation != scope.generation.value
                        or (proof.connection_id, proof.connection_generation) != (channel.connection_id,
                                                                                   channel.connection_generation)
                        or rollout.thread_id != mapping.codex_thread_id):
                    return
                root = str(await asyncio.to_thread(Path(workspace_root).resolve, strict=True))
                await asyncio.to_thread(self._record, scope, runtime_scope, mapping, frame['operation_id'],
                                        proof, rollout, root)
        except (CoreError, TimeoutError, ValueError, OSError, sqlite3.Error):
            _LOG.debug('Saved Codex history observation deferred or unavailable.')
        except OktoNexusError as error:
            # Optional evidence cannot turn an authorized canonical close into
            # subject-wide containment when the read fence or storage changed.
            _LOG.debug('Saved Codex history observation refused: code=%s', error.code.value)

    def _record(self, scope, runtime_scope, mapping, close_id, proof, rollout, root):
        owner = self.owner
        with owner.factory.unit_of_work() as uow:
            if owner._native_presentation_mapping(scope, runtime_scope, uow=uow) != mapping:
                return
            # Host file identities can exceed the R4 wire's integer range.
            witness = json.dumps({
                'scope': runtime_scope, 'launch_build': asdict(mapping.launch_build),
                'configuration_hash': mapping.codex_configuration_hash,
                'process': asdict(proof.process), 'rollout': asdict(rollout), 'workspace_root': root,
            }, separators=(',', ':'), allow_nan=False)
            uow.connection.execute("""
                INSERT INTO embedded_codex_saved_contexts (
                    server_id, executor_id, session_id, owner_generation, opening_operation_id,
                    close_operation_id, stream_epoch, witness_json, captured_at, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'CAPTURED')
                ON CONFLICT(server_id, executor_id, close_operation_id) DO NOTHING
            """, (proof.key.server_id, proof.key.executor_id, proof.key.session_id, proof.owner_generation,
                  proof.target.opening_operation_id, close_id, proof.target.stream_epoch, witness,
                  owner.deps.clock.now_iso()))

    def _ready(self, uow, close_id):
        channel = self.owner.channel
        row = uow.connection.execute(_READY, {'server_id': channel.server_id,
            'executor_id': channel.executor_id, 'close_id': close_id}).fetchone()
        return dict(row) if row is not None else None

    def _next(self, close_id):
        owner = self.owner
        with owner.factory.unit_of_work(write=False) as uow:
            owner.verify(uow=uow)
            if close_id is not None:
                return None, self._ready(uow, close_id)
            row = uow.connection.execute("""
                SELECT rowid, close_operation_id FROM embedded_codex_saved_contexts
                WHERE server_id=? AND executor_id=? AND status='CAPTURED' AND rowid>?
                ORDER BY rowid LIMIT 1
            """, (owner.channel.server_id, owner.channel.executor_id, self._after)).fetchone()
            return (row['rowid'], self._ready(uow, row['close_operation_id'])) if row else (0, None)

    async def reconcile(self, close_id=None):
        """Resolve one exact durable candidate, including after a dispatch restart."""
        if not self.owner.deps.config.runtime_session_interaction_enabled:
            return
        try:
            async with asyncio.timeout(_OBSERVATION_TIMEOUT):
                cursor, candidate = await asyncio.to_thread(self._next, close_id)
                if cursor is not None:
                    self._after = cursor
                if candidate is not None:
                    await self._verify(candidate)
        except (CoreError, TimeoutError, ValueError, TypeError, KeyError, OSError, sqlite3.Error):
            _LOG.debug('Saved Codex history verification deferred or unavailable.')
        except OktoNexusError as error:
            if error.code == ErrorCode.DB_ERROR and not error.retryable:
                _LOG.warning('Saved Codex history verification could not persist evidence.')

    async def _verify(self, candidate):
        host = self.owner.host
        key = SessionKey(*(candidate[field] for field in ('server_id', 'executor_id', 'session_id')))
        close_key = OperationKey(key.server_id, key.executor_id, candidate['close_operation_id'])
        witness = json.loads(candidate['witness_json'])
        ledger = await host._ledger()

        async def retirement(journal):
            bound = json.loads(candidate['close_binding'])
            if bound['action'] != 'runtime.close':
                raise CoreError('SCOPE_MISMATCH', 'saved_codex_context')
            close = await journal.get_receipt(close_key)
            closing = project_r4_bound_receipt(bound, close,
                key=close_key, receipt_revision=candidate['receipt_revision'])
            birth = await journal.get_process_birth(key)
            if (closing != json.loads(candidate['canonical_frame']) or birth is None
                    or asdict(birth) != witness['process']):
                raise CoreError('SCOPE_MISMATCH', 'saved_codex_context')
            page = await journal.claimed_sessions(key.server_id, key.executor_id, limit=2)
            if len(page.claims) != 1 or page.next_after_rowid is not None:
                raise CoreError('RECONCILIATION_REQUIRED', 'saved_codex_context')
            claim = page.claims[0]
            if (claim.key != key or claim.opening_operation_id != candidate['opening_operation_id']
                    or claim.opening_owner_generation != candidate['owner_generation']):
                raise CoreError('SCOPE_MISMATCH', 'saved_codex_context')
            opening = await journal.get_receipt(OperationKey(key.server_id, key.executor_id, claim.opening_operation_id))
            slot = await ledger.owned_slot_state(key)
            return project_r4_resource_release(json.loads(candidate['opening_binding']), claim, slot, opening)

        fact = await host.with_history(executor_id=key.executor_id, session_id=key.session_id, read=retirement)
        document = witness['rollout']
        prior = CodexRolloutEvidence(**(document | {
            name: tuple(document[name]) for name in ('relative_path', 'home_identity', 'file_identity')
        }))
        path = Path(prior.state_home).joinpath(*prior.relative_path)
        checked = await asyncio.to_thread(observe_rollout, prior.state_home, str(path),
                                          prior.thread_id, witness['workspace_root'])
        await asyncio.to_thread(self._resolve, candidate, fact['proof_digest'] if checked == prior else None)

    def _resolve(self, candidate, release_digest):
        owner = self.owner
        with owner.factory.unit_of_work() as uow:
            owner.verify(uow=uow)
            if self._ready(uow, candidate['close_operation_id']) != candidate:
                return
            uow.connection.execute("""
                UPDATE embedded_codex_saved_contexts SET status=?, resolved_at=?, release_digest=?
                WHERE server_id=? AND executor_id=? AND close_operation_id=? AND status='CAPTURED'
            """, ('VERIFIED' if release_digest else 'FILE_CHANGED', owner.deps.clock.now_iso(), release_digest,
                  candidate['server_id'], candidate['executor_id'], candidate['close_operation_id']))
