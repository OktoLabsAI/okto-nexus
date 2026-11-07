"""Acquire historical Core birth and an exact OS identity without starting work."""
from functools import partial
import time

import anyio
from nexus_connector_core import CoreError
from nexus_connector_core.models import ProcessBirthRecord

from ..adapters.outbound.observation.windows_identity import open_process_identity
from ..application.observation_correlation_service import refused
from ..domain.herdr_observations import HerdrObservationError
from ..domain.observation_correlation import ObservationCorrelationError, normalize_native_record, verify_native_birth
from ..errors import OktoNexusError


class NativeObservationCorrelationProof:
    def __init__(self, state, *, identity_guard=open_process_identity, monotonic=time.monotonic):
        self.state, self.identity_guard = state, identity_guard
        self.monotonic = monotonic

    async def select(self, service, *, context, observed_instance_id, body):
        owner = getattr(self.state, 'embedded_dispatch_owner', None)
        host = getattr(self.state, 'embedded_core_host', None)
        session_holder = []
        deadline = self.monotonic() + 5

        def check_budget():
            if self.monotonic() >= deadline:
                raise TimeoutError

        def verify_owner(*, uow, selection, native):
            # This callback is invoked only after current operator authentication.
            if (owner is None or host is None or owner.host is not host
                    or getattr(self.state, 'embedded_dispatch_owner', None) is not owner
                    or getattr(self.state, 'embedded_core_host', None) is not host
                    or owner._stopping.is_set() or host._closing or host._history_closing
                    or owner.failure is not None or owner.state_failure is not None
                    or owner.recovery_failure is not None):
                refused('OBSERVATION_CORRELATION_OWNER_UNAVAILABLE')
            channel = owner.channel
            if (channel.server_id != selection['server_id'] or channel.executor_id != selection['executor_id']
                    or native['owner_instance_id'] != channel.connection_id
                    or native['executor_generation'] != channel.connection_generation):
                refused('OBSERVATION_CORRELATION_OWNER_CHANGED')
            session = owner.sessions.get(selection['session_id'])
            if (session is None or session.get('executor') is None or session.get('opening')
                    or session.get('recovering') or session_holder and session_holder[0] is not session):
                refused('OBSERVATION_CORRELATION_SESSION_UNAVAILABLE')
            scope = session['scope']
            if (any(scope.get(name) != selection[name] for name in (
                    'server_id', 'executor_id', 'session_id', 'binding_id',
                    'workspace_binding_id', 'session_owner_generation'))
                    or scope.get('agent_id') != native['subject_agent_id']
                    or scope.get('workspace_id') != native['workspace_id']):
                refused('OBSERVATION_CORRELATION_SESSION_CHANGED')
            owner.verify(uow=uow)
            if not session_holder:
                session_holder.append(session)

        try:
            with anyio.fail_after(5):
                prepared = await anyio.to_thread.run_sync(partial(service.prepare,
                    context=context, observed_instance_id=observed_instance_id, body=body, verify_owner=verify_owner))
                check_budget()
                selected, evidence = prepared['selection'], prepared['evidence']
                record = await host.read_existing_process_birth(**{name: selected[name]
                    for name in ('server_id', 'executor_id', 'session_id')})
                if not isinstance(record, ProcessBirthRecord):
                    refused('OBSERVATION_CORRELATION_BIRTH_UNAVAILABLE')
                native = normalize_native_record(dict(server_id=record.key.server_id, executor_id=record.key.executor_id,
                    session_id=record.key.session_id, opening_operation_id=record.opening_operation_id,
                    platform=record.evidence.platform, pid=record.evidence.pid, birth_token=record.evidence.birth_token))
                # Reject mismatched caller PIDs before opening any OS handle.
                if (any(native[name] != selected[name] for name in ('server_id', 'executor_id', 'session_id'))
                        or native['opening_operation_id'] != selected['open_operation_id']
                        or native['pid'] != evidence['pid']):
                    refused('OBSERVATION_CORRELATION_PROOF_MISMATCH')

                def finish():
                    check_budget()
                    service.revalidate(context=context, prepared=prepared, verify_owner=verify_owner)
                    check_budget()
                    # No UoW is open while querying OS identity. The proof records
                    # this instant only, not continuing liveness after commit.
                    with self.identity_guard(evidence['pid']) as guard:
                        actual = guard.require_alive()
                        check_budget()
                        os_identity = {name: getattr(actual, name) for name in
                            ('host_id', 'pid', 'creation_filetime', 'image_path')}
                        proof = verify_native_birth(selected, evidence, native_record=native, os_identity=os_identity)
                        verified_at = service.clock.now_iso()
                        return service.commit(context=context, prepared=prepared, proof=proof,
                            verified_at=verified_at, verify_owner=verify_owner, check_budget=check_budget)

                # The worker must finish/close its handle even if the client
                # disconnects. This is an admission budget, not a hard bound on
                # a blocking OS call or SQLite commit. No writes are admitted
                # after expiry; a lost response is recovered with exact GET/CAS.
                return await anyio.to_thread.run_sync(finish)
        except ObservationCorrelationError as error:
            refused(error.code)
        except (CoreError, HerdrObservationError, TimeoutError):
            raise OktoNexusError('OBSERVATION_CORRELATION_UNAVAILABLE',
                'The selected native birth comparison could not be established.', {}) from None
