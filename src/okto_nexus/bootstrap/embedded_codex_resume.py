"""Carry the verified source into one exact local Codex opening."""

import asyncio
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path

from nexus_connector_core import CodexResumeGrant, CoreError
from nexus_connector_core.native.codex_rollout import observe_rollout
from nexus_connector_core.protocol import strict_json

from ..application.execution_saved_resume import (
    require_saved_source_exclusive,
    require_saved_source_settled,
    rollout_evidence,
    saved_opening_profile,
    saved_source,
)
from ..errors import OktoNexusError
from .local_mcp_home import _plain


def _refuse(code='PROFILE_DRIFT'):
    return CoreError(code, 'saved_codex_resume', retry_safe=True)


def native_opening_for_operation(owner, frame):
    """Read the durable saved lineage or the operator's explicit empty opening."""
    with owner.factory.unit_of_work(write=False) as uow:
        owner.verify(uow=uow)
        row = uow.connection.execute("""
            SELECT s.saved_resume_json, (
                SELECT json_extract(i.resolved_json, '$.saved_resume') FROM execution_client_intents i
                JOIN execution_operations p ON p.server_id=s.server_id AND p.executor_id=s.executor_id
                    AND p.operation_id=s.open_operation_id AND p.actor_agent_id=i.actor_agent_id
                WHERE i.server_id=s.server_id AND i.operation_id=s.open_operation_id
                  AND json_type(i.resolved_json, '$.saved_resume') IS NOT NULL
                LIMIT 1
            ) AS saved_intent, EXISTS (
                SELECT 1 FROM execution_client_intents i
                JOIN execution_operations p ON p.server_id=s.server_id AND p.executor_id=s.executor_id
                    AND p.operation_id=s.open_operation_id AND p.actor_agent_id=i.actor_agent_id
                WHERE i.server_id=s.server_id AND i.operation_id=s.open_operation_id
                  AND i.actor_agent_id='operator' AND i.session_selection='explicit'
                  AND i.initial_turn_json IS NULL
            ) AS explicit_empty
            FROM execution_sessions s
            WHERE s.server_id=? AND s.executor_id=? AND s.session_id=? AND s.open_operation_id=?
        """, tuple(frame[k] for k in ('server_id', 'executor_id', 'session_id', 'operation_id'))).fetchone()
        if row is None:
            raise _refuse('RECONCILIATION_REQUIRED')
        lineage = json.loads(row['saved_resume_json'] or 'null')
        if lineage != json.loads(row['saved_intent'] or 'null'):
            raise _refuse('RECONCILIATION_REQUIRED')
        if lineage is None:
            return None, bool(row['explicit_empty'])
        if not owner.deps.config.runtime_session_interaction_enabled:
            raise _refuse('CAPABILITY_UNSUPPORTED')
        if frame['payload']['adapter_id'] == 'claude_stream':
            from .embedded_claude_resume import SavedClaudeOpening
            return SavedClaudeOpening(owner, frame, lineage), False
        return SavedCodexOpening(owner, frame, lineage), False


def read_retired_source(owner, frame, lineage, *, ready=False):
    with owner.factory.unit_of_work(write=False) as uow:
        owner.verify(uow=uow)
        row = uow.connection.execute("""
            SELECT saved_resume_json, native_launch_build_json, owner_generation, lifecycle_state
            FROM execution_sessions
            WHERE server_id=? AND executor_id=? AND session_id=? AND open_operation_id=?
        """, tuple(frame[k] for k in ('server_id', 'executor_id', 'session_id', 'operation_id'))).fetchone()
        states = ('OPEN_PENDING', 'READY') if ready else ('OPEN_PENDING',)
        if (row is None or row['owner_generation'] != frame['session_owner_generation']
                or row['lifecycle_state'] not in states
                or json.loads(row['saved_resume_json'] or 'null') != lineage):
            raise _refuse('STALE_GENERATION')
        try:
            current, witness = saved_source(uow.connection, frame, lineage['source_session_id'],
                lineage['source_session_generation'], adapter_id=frame['payload']['adapter_id'])
            require_saved_source_exclusive(uow.connection, frame, lineage, successor=frame['session_id'])
            require_saved_source_settled(uow.connection, frame, lineage['source_session_id'])
        except OktoNexusError as error:
            raise _refuse('RECONCILIATION_REQUIRED') from error
        if current != lineage or json.loads(row['native_launch_build_json'] or 'null') != witness['launch_build']:
            raise _refuse()
        return witness


class SavedCodexOpening:
    callback_key = 'codex_resume'
    target_key = 'resume_thread_id'

    def __init__(self, owner, frame, lineage):
        self.owner = owner
        self.frame = dict(frame)
        self.lineage = lineage
        self.witness = self._read_source()
        self.rollout = rollout_evidence(self.witness['rollout'])
        self.thread_id = self.rollout.thread_id
        self.target = self.thread_id

    def _read_source(self):
        return read_retired_source(self.owner, self.frame, self.lineage)

    def _check_file(self, prepared):
        if self._read_source() != self.witness or Path(prepared.cwd) != Path(self.witness['workspace_root']):
            raise _refuse()
        prior = self.witness.get('opening_profile')
        if prior is not None:
            current = saved_opening_profile(prepared)
            if any(current.get(key) != prior.get(key) for key in ('root_fingerprint', 'resume_configuration_sha256')):
                raise _refuse()
        location = Path(self.rollout.state_home).joinpath(*self.rollout.relative_path)
        current = observe_rollout(self.rollout.state_home, str(location), self.thread_id, prepared.cwd)
        if current != self.rollout:
            raise _refuse()
        return location

    async def grant(self, prepared, session_id, context):
        await asyncio.to_thread(self._check_file, prepared)
        expected = self.frame
        if (session_id != expected['session_id'] or any(getattr(context, field) != expected[field]
                for field in ('server_id', 'executor_id', 'binding_id', 'agent_id', 'workspace_id',
                              'session_owner_generation', 'authorization_revision', 'configuration_revision'))):
            raise _refuse('STALE_GENERATION')
        return CodexResumeGrant(self.thread_id, session_id, context.server_id, context.executor_id,
                                context.binding_id, context.agent_id, context.workspace_id,
                                context.session_owner_generation, prepared.candidate.fingerprint,
                                prepared.root_fingerprint, prepared.profile_fingerprint, True, True, True)

    async def environment(self, resolve, local_launch, prepared):
        environment = await resolve(prepared)
        home = local_launch.tools['home'] if local_launch is not None and local_launch.tools else None
        await asyncio.to_thread(self._stage, prepared, environment.get('CODEX_HOME'), home)
        return environment

    def _stage(self, prepared, state_home, owned_home):
        source = self._check_file(prepared)
        if not state_home or not Path(state_home).is_absolute():
            raise _refuse()
        destination_home = Path(state_home)
        if destination_home != Path(self.rollout.state_home):
            if owned_home is None or destination_home != owned_home.config.parent:
                raise _refuse()
            try:
                owned_home.require_current()
                destination = destination_home.joinpath(*self.rollout.relative_path)
                _publish_rollout(source, destination, destination_home, self.rollout.sha256)
                found = observe_rollout(str(destination_home), str(destination), self.thread_id, prepared.cwd)
                if found is None or found.sha256 != self.rollout.sha256:
                    raise _refuse()
                owned_home.require_current()
            except (OSError, ValueError, TypeError, KeyError, RecursionError):
                raise _refuse() from None
        if self._read_source() != self.witness:
            raise _refuse()


def _publish_rollout(source, destination, state_home, digest):
    """Publish just the exact history in a newly approved per-session profile."""
    # Only the source selected by the native engine may be copied. A fork or
    # paginated history may resolve other files from its old state directory.
    with source.open('rb') as input_file:
        first = input_file.readline(1024 * 1024 + 1)
        metadata = strict_json(first.decode())['payload']
        if any(metadata.get(key) is not None for key in ('history_base', 'forked_from_id', 'parent_thread_id')):
            raise _refuse('CAPABILITY_UNSUPPORTED')
        parent = state_home
        for part in destination.relative_to(state_home).parts[:-1]:
            parent = parent / part
            _plain(parent)
            parent.mkdir(exist_ok=True)
            _plain(parent)
        _plain(destination)
        if destination.exists():
            return
        with tempfile.NamedTemporaryFile(mode='w+b', dir=parent, prefix='.nexus-rollout-', delete=False) as output:
            temporary = Path(output.name)
            try:
                output.write(first)
                shutil.copyfileobj(input_file, output, length=1024 * 1024)
                output.flush()
                os.fsync(output.fileno())
                output.seek(0)
                if hashlib.file_digest(output, 'sha256').hexdigest() != digest:
                    raise _refuse()
            except BaseException:
                output.close()
                temporary.unlink(missing_ok=True)
                raise
        try:
            if os.name == 'nt':
                # Windows rename publishes atomically and refuses an existing
                # destination, including on recovery of an interrupted copy.
                temporary.rename(destination)
            else:
                os.link(temporary, destination)
        except FileExistsError:
            _plain(destination)
        finally:
            temporary.unlink(missing_ok=True)
