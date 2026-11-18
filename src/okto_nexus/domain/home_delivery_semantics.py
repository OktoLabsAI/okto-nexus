"""Read-only delivery meaning; never execution or verification authority."""
import re
from typing import Literal, TypedDict

from .attention import digest


class DeliverySemantics(TypedDict):
    version: Literal[1]
    scope: Literal['turn', 'handoff', 'external_report']
    evidence: Literal['canonical', 'reported']
    execution_outcome: Literal['succeeded', 'failed', 'cancelled', 'rejected', 'unknown', 'not_applicable']
    task_state: Literal['open', 'claimed', 'verifying', 'completed', 'rejected', 'cancelled', 'unknown', 'not_applicable']
    verification: Literal['approved', 'rejected', 'pending', 'unknown', 'not_applicable']
    verification_evidence_ref: str | None
    cleanup: Literal['pending', 'complete', 'unknown', 'not_applicable']
    content_state: Literal['available', 'pending', 'not_captured', 'unavailable']
    historical: bool
    semantic_revision: str


def delivery_reference(workspace_id, handoff_id, claim_epoch, persisted_result):
    """Hash the exact persisted delivery, not a caller's parsed replacement."""
    if type(claim_epoch) is not int or claim_epoch < 0:
        raise ValueError('A delivery reference requires its canonical claim epoch.')
    revision = 'sha256:' + digest([1, workspace_id, handoff_id, claim_epoch, persisted_result])
    return {'version': 1, 'kind': 'handoff_delivery', 'workspace_id': workspace_id,
        'handoff_id': handoff_id, 'claim_epoch': claim_epoch, 'delivery_revision': revision}


def _seal(value, revision_source=None):
    return dict(value, semantic_revision=digest([value, revision_source]))


def project(facts) -> DeliverySemantics:
    """Compose independently proven dimensions from one authorized SQL fact."""
    native = bool(facts.get('operation_id'))
    handoff = facts.get('handoff_id')
    epoch, current = facts.get('claim_epoch'), facts.get('current_epoch')
    historical = bool(handoff and type(epoch) is int and type(current) is int and epoch != current)
    stage = facts.get('stage')
    task = str(facts.get('handoff_status') or (stage if not native else '')).lower()
    task = task if task in {'open', 'claimed', 'verifying', 'completed', 'rejected', 'cancelled'} else 'unknown'
    outcome = {'SUCCEEDED': 'succeeded', 'FAILED': 'failed', 'CANCELLED': 'cancelled'}.get(stage, 'unknown') if native else 'not_applicable'
    verification, evidence_ref = 'unknown', None
    proof = facts.get('verification_proof')
    expected_revision = facts.get('delivery_revision')
    if not handoff:
        task, verification = 'not_applicable', 'not_applicable'
    elif (isinstance(proof, dict) and type(proof.get('version')) is int and proof['version'] == 1
            and proof.get('kind') == 'handoff_delivery'
            and proof.get('workspace_id') == facts.get('workspace_id')
            and proof.get('handoff_id') == handoff and type(proof.get('claim_epoch')) is int
            and proof['claim_epoch'] == epoch and isinstance(expected_revision, str)
            and re.fullmatch(r'sha256:[0-9a-f]{64}', expected_revision)
            and proof.get('delivery_revision') == expected_revision
            and type(proof.get('event_claim_epoch')) is int and proof['event_claim_epoch'] == epoch
            and proof.get('event_delivery_revision') == expected_revision
            and type(proof.get('event_id')) is int and proof['event_id'] > 0
            and type(proof.get('submission_event_id')) is int
            and 0 < proof['submission_event_id'] < proof['event_id']
            and isinstance(proof.get('verified_by'), str) and proof['verified_by']
            and proof.get('verified_by') == proof.get('actor_agent_id')
            and proof.get('verdict') in {'pass', 'fail'}
            and proof.get('event_type') == ('handoff.completed' if proof['verdict'] == 'pass' else 'handoff.verification_failed')):
        verification = 'approved' if proof['verdict'] == 'pass' else 'rejected'
        evidence_ref = 'handoff-verification:' + str(proof['event_id']) + ':' + digest(proof)
    elif not historical and task == 'verifying':
        verification = 'pending'
    elif facts.get('verification_required') is False:
        verification = 'not_applicable'
    if native:
        content = 'available' if facts.get('terminal_sequence') is not None else 'pending'
        cleanup = {'REQUESTED': 'pending', 'RELEASED': 'complete'}.get(facts.get('containment_state'), 'unknown')
    else:
        content = 'available' if facts.get('handoff_content_available') else 'unavailable' if historical else 'not_captured'
        cleanup = 'not_applicable'
    return _seal({'version': 1, 'scope': 'turn' if native else 'handoff', 'evidence': 'canonical',
        'execution_outcome': outcome, 'task_state': task, 'verification': verification,
        'verification_evidence_ref': evidence_ref, 'cleanup': cleanup, 'content_state': content,
        'historical': historical})


def reported_semantics(report) -> DeliverySemantics:
    """An explicit external completion reports a fact; it cannot verify runtime."""
    return _seal({'version': 1, 'scope': 'external_report', 'evidence': 'reported',
        'execution_outcome': 'unknown', 'task_state': 'not_applicable', 'verification': 'unknown',
        'verification_evidence_ref': None, 'cleanup': 'not_applicable', 'content_state': 'not_captured',
        'historical': False}, report.get('source_revision'))
