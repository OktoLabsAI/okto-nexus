"""Accept one contained session's resource proof without executor recovery."""
from dataclasses import dataclass
from typing import Protocol

from nexus_connector_core import r4_resource_release_digest
from nexus_connector_core.session_release import (
    decode_session_release, encode_session_release, session_release_accepted,
)

from ..errors import ErrorCode, OktoNexusError


@dataclass(frozen=True)
class SessionReleaseObservation:
    scope: dict
    denial: dict
    opening_operation_id: str
    opening_intent_hash: str
    owner_generation: int
    opening_receipt: dict | None
    receipt_count: int
    receipt_digest: str
    stream_epoch: str | None
    committed_sequence: int
    gap: bool
    previous_proof: dict | None
    revision: tuple


class SessionReleaseRepository(Protocol):
    def observe(self, uow, request, channel) -> SessionReleaseObservation | None: ...
    def unchanged(self, uow, request, channel, revision) -> bool: ...
    def close(self, uow, request) -> None: ...


class ExecutionSessionRelease:
    def __init__(self, *, factory, repository: SessionReleaseRepository, containment, project):
        self.factory, self.repository, self.containment, self.project = factory, repository, containment, project

    def accept(self, request, *, channel):
        request = decode_session_release(encode_session_release(request))
        def refuse():
            raise OktoNexusError(ErrorCode.CONFLICT,
                'Session release requires matching ownership, published receipts and a drained event stream.', {})
        if request['type'] != 'session.release' or any(request[k] != getattr(channel, k) for k in
                ('server_id','executor_id','connection_id','connection_generation')):
            refuse()
        scope = request['scope']
        # Full historical receipt validation can be expensive. Keep it outside
        # the writer transaction; a compact revision CAS fences the final commit.
        with self.factory.unit_of_work(write=False) as uow:
            observed = self.repository.observe(uow, request, channel)
            if (observed is None or observed.scope != scope or observed.denial['scope'] != scope
                    or any(observed.denial[k] != request[k] for k in ('connection_id','connection_generation'))
                    or observed.owner_generation != scope['session_owner_generation']
                    or observed.opening_operation_id != request['opening_operation_id']
                    or observed.opening_intent_hash != request['opening_intent_hash']):
                refuse()
            if observed.previous_proof is not None:
                # Lost ACK: preserve the exact original committed report. A new
                # release ID or changed history must not replace that evidence.
                if observed.previous_proof.get('request') != request:
                    refuse()
                return session_release_accepted(request)
            receipt = observed.opening_receipt
            if (receipt is None or receipt['session_id'] != scope['session_id']
                    or receipt['operation_id'] != observed.opening_operation_id
                    or receipt['intent_hash'] != observed.opening_intent_hash
                    or not receipt['possible_effect']
                    or receipt['stage'] not in ('SUBMISSION_STARTED','SUBMITTED','RUNNING','OUTCOME_UNKNOWN','SUCCEEDED','FAILED')
                    or observed.receipt_count != request['receipt_count']
                    or observed.receipt_digest != request['receipt_digest']
                    or observed.gap or observed.committed_sequence != request['sequence']
                    or observed.stream_epoch not in (None, request['stream_epoch'])
                    or request['sequence'] > 0 and observed.stream_epoch != request['stream_epoch']):
                refuse()
            digest = r4_resource_release_digest(server_id=channel.server_id, executor_id=channel.executor_id,
                session_id=scope['session_id'], opening_operation_id=observed.opening_operation_id,
                opening_intent_hash=observed.opening_intent_hash, owner_generation=observed.owner_generation)
            if request['proof_digest'] != digest:
                refuse()
            proof = dict(request=request, ownership=dict(session_id=scope['session_id'],
                owner_generation=observed.owner_generation, process_state='EXITED', proof_digest=digest),
                stream=dict(session_id=scope['session_id'], stream_epoch=request['stream_epoch'], sequence=request['sequence']))
        with self.factory.unit_of_work() as uow:
            if not self.repository.unchanged(uow, request, channel, observed.revision):
                refuse()
            self.repository.close(uow, request)
            self.project(uow, channel, scope['session_id'], proof)
            self.containment.record_verified_release(uow, channel=channel, session_id=scope['session_id'],
                owner_generation=observed.owner_generation, proof=proof)
        return session_release_accepted(request)  # ACK only after the commit.
